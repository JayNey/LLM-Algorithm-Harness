"""Codeforces public problemset importer."""

from __future__ import annotations

import html
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

from src.importers.base import ImportResult, ProblemImporter
from src.importers.local_json import LocalJsonImporter
from src.models import Problem
from src.utils.logging import get_logger

logger = get_logger(__name__)


class _TextParser(HTMLParser):
    """Small dependency-free HTML to text converter for public statements."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"br", "p", "div", "li", "section", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "section", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def text(self) -> str:
        value = html.unescape("".join(self.parts))
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n[ \t]+", "\n", value)
        return re.sub(r"\n{3,}", "\n\n", value).strip()


class CodeforcesImporter(ProblemImporter):
    """Import public Codeforces statements and examples without login."""

    api_endpoint = "https://codeforces.com/api/problemset.problems"
    problem_url = "https://codeforces.com/problemset/problem/{contest_id}/{index}"
    tag_mapping = {
        "dp": "dynamic-programming",
        "graphs": "graph",
        "trees": "tree",
        "greedy": "greedy",
        "math": "math",
        "data structures": "data-structures",
        "binary search": "binary-search",
    }

    def __init__(
        self,
        *,
        contest: int | str | None = None,
        min_rating: int | None = None,
        max_rating: int | None = None,
        tags: list[str] | None = None,
        limit: int | None = None,
        session=None,
        timeout: float = 20.0,
        retries: int = 2,
        backoff_seconds: float = 0.5,
        sleep=time.sleep,
    ):
        if min_rating is not None and max_rating is not None and min_rating > max_rating:
            raise ValueError("min_rating cannot exceed max_rating")
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        self.contest = str(contest) if contest is not None else None
        self.min_rating = min_rating
        self.max_rating = max_rating
        self.tags = {tag.strip().lower() for tag in tags or [] if tag.strip()}
        self.limit = limit
        self.session = session or (requests.Session() if requests else None)
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.sleep = sleep
        self.transform_failures: list[dict[str, Any]] = []
        self.selected_problem_ids: list[str] = []

    def fetch_problems(self, source: str) -> list[dict[str, Any]]:
        """Fetch and filter the public problemset, then fetch statements."""
        if self.session is None:
            raise ImportError("requests package is required for Codeforces import")
        response = self._request(self.api_endpoint)
        payload = response.json()
        if payload.get("status") != "OK":
            raise RuntimeError(f"Codeforces API error: {payload.get('comment', 'unknown error')}")
        problems = (payload.get("result") or {}).get("problems") or []
        selected = [problem for problem in problems if self._matches(problem)]
        selected.sort(key=lambda item: (item.get("contestId", 0), str(item.get("index", ""))))
        if self.limit:
            selected = selected[: self.limit]
        output = []
        for problem in selected:
            if str(problem.get("type", "")).lower() == "interactive":
                continue
            item = dict(problem)
            contest_id = item.get("contestId")
            index = item.get("index")
            if contest_id is None or not index:
                item["_statement_error"] = "missing contestId or index"
                output.append(item)
                continue
            item["_source_url"] = self.problem_url.format(contest_id=contest_id, index=index)
            try:
                statement = self._request(item["_source_url"]).text
                item["_statement_html"] = statement
            except Exception as exc:
                item["_statement_error"] = str(exc)
            output.append(item)
        self.selected_problem_ids = [self._problem_id(item) for item in output]
        return output

    def transform_to_schema(self, raw_data: Any) -> list[Problem]:
        items = raw_data if isinstance(raw_data, list) else [raw_data]
        self.transform_failures = []
        transformed = []
        for index, item in enumerate(items):
            try:
                transformed.append(self._transform_problem(item))
            except Exception as exc:
                self.transform_failures.append(
                    {"index": index, "problem_id": self._problem_id(item), "error": str(exc)}
                )
                logger.warning("codeforces_problem_transform_failed", index=index, error=str(exc))
        return transformed

    def detect_duplicates(self, problems, existing_problems, update_strategy):
        return LocalJsonImporter().detect_duplicates(problems, existing_problems, update_strategy)

    def generate_report(self, result: ImportResult, source: str, output_path: str, preview: bool):
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "codeforces",
            "input_path": source,
            "output_path": output_path,
            "preview_mode": preview,
            "filters": {
                "contest": self.contest,
                "min_rating": self.min_rating,
                "max_rating": self.max_rating,
                "tags": sorted(self.tags),
                "limit": self.limit,
            },
            "summary": {
                "total_attempted": result.total_attempted,
                "successful": len(result.successful),
                "failed": len(result.failed),
                "duplicates_skipped": len(result.duplicates_skipped),
                "duplicates_overwritten": len(result.duplicates_overwritten),
            },
            "successful_problems": [problem.problem_id for problem in result.successful],
            "failed_problems": result.failed,
            "warnings": result.warnings,
            "selected_problem_ids": self.selected_problem_ids,
        }

    def _request(self, url: str):
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(
                    url,
                    headers={"User-Agent": "LLM-Algorithm-Harness/0.1"},
                    timeout=self.timeout,
                )
                status = int(getattr(response, "status_code", 200))
                if status == 404:
                    raise ValueError(f"Codeforces resource not found: {url}")
                if status in {403, 429} or status >= 500:
                    raise RuntimeError(f"Codeforces transient HTTP error: {status}")
                if status >= 400:
                    raise ValueError(f"Codeforces request failed: HTTP {status}")
                return response
            except ValueError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                self.sleep(self.backoff_seconds * (2**attempt))
        raise RuntimeError(f"Unable to fetch Codeforces resource: {last_error}") from last_error

    def _matches(self, problem: dict[str, Any]) -> bool:
        if self.contest is not None and str(problem.get("contestId")) != self.contest:
            return False
        rating = problem.get("rating")
        if self.min_rating is not None and (rating is None or int(rating) < self.min_rating):
            return False
        if self.max_rating is not None and (rating is None or int(rating) > self.max_rating):
            return False
        tags = {str(tag).lower() for tag in problem.get("tags") or []}
        return not self.tags or bool(tags & self.tags)

    @classmethod
    def _problem_id(cls, item: dict[str, Any]) -> str:
        return f"codeforces_{item.get('contestId', 'unknown')}_{item.get('index', 'unknown')}"

    def _transform_problem(self, item: dict[str, Any]) -> Problem:
        problem_id = self._problem_id(item)
        rating = item.get("rating")
        difficulty = self.map_difficulty(rating)
        tags = [self.tag_mapping.get(str(tag).lower(), str(tag)) for tag in item.get("tags") or []]
        statement_html = item.get("_statement_html") or ""
        description, input_text, output_text, samples = self.parse_statement(statement_html)
        notes = []
        if item.get("_statement_error"):
            notes.append(f"Statement unavailable: {item['_statement_error']}")
        if not description:
            notes.append("Codeforces statement requires manual completion")
        public_cases = [
            {"input": sample[0], "expected_output": sample[1]}
            for sample in samples
            if sample[0].strip() and sample[1].strip()
        ]
        if not public_cases:
            notes.append("No reliable public samples were parsed")
        return Problem(
            schema_version="1.1",
            problem_id=problem_id,
            title=str(item.get("name") or problem_id),
            description=description or str(item.get("name") or problem_id),
            difficulty=difficulty,
            tags=tags,
            constraints=input_text or None,
            source_platform="codeforces",
            source_problem_id=f"{item.get('contestId', 'unknown')}_{item.get('index', 'unknown')}",
            source_url=item.get("_source_url")
            or self.problem_url.format(contest_id=item.get("contestId"), index=item.get("index")),
            source_version="codeforces-api-v1",
            input_output_mode="stdin_stdout",
            entry_point="main()",
            public_test_cases=public_cases,
            needs_manual_completion=bool(notes),
            manual_completion_notes=notes,
            source_metadata={
                "rating": rating,
                "contest_id": item.get("contestId"),
                "index": item.get("index"),
                "output_specification": output_text,
            },
        )

    @staticmethod
    def map_difficulty(rating: Any) -> str:
        if rating is None:
            return "medium"
        rating = int(rating)
        if rating <= 1400:
            return "easy"
        if rating <= 2100:
            return "medium"
        return "hard"

    @staticmethod
    def parse_statement(content: str) -> tuple[str, str, str, list[tuple[str, str]]]:
        if not content:
            return "", "", "", []
        statement = re.search(r'<div[^>]*class="[^"]*problem-statement[^"]*"[^>]*>(.*)</div>\s*</div>\s*$', content, re.S | re.I)
        body = statement.group(1) if statement else content
        samples = []
        for block in re.findall(r'<div[^>]*class="[^"]*sample-test[^"]*"[^>]*>(.*?)</div>\s*</div>', body, re.S | re.I):
            input_match = re.search(r'<div[^>]*class="[^"]*input[^"]*"[^>]*>.*?<pre[^>]*>(.*?)</pre>', block, re.S | re.I)
            output_match = re.search(r'<div[^>]*class="[^"]*output[^"]*"[^>]*>.*?<pre[^>]*>(.*?)</pre>', block, re.S | re.I)
            if input_match and output_match:
                samples.append((_clean_text(input_match.group(1)), _clean_text(output_match.group(1))))
        body_without_samples = re.sub(r'<div[^>]*class="[^"]*sample-tests[^"]*"[^>]*>.*', "", body, flags=re.S | re.I)
        input_match = re.search(r'<div[^>]*class="[^"]*input-specification[^"]*"[^>]*>(.*?)</div>\s*</div>', body, re.S | re.I)
        output_match = re.search(r'<div[^>]*class="[^"]*output-specification[^"]*"[^>]*>(.*?)</div>\s*</div>', body, re.S | re.I)
        input_text = _clean_text(input_match.group(1)) if input_match else ""
        output_text = _clean_text(output_match.group(1)) if output_match else ""
        return _clean_text(body_without_samples), input_text, output_text, samples


def _clean_text(content: str) -> str:
    parser = _TextParser()
    parser.feed(content)
    return parser.text()
