"""LeetCode public question importer.

The importer intentionally uses only the public question GraphQL query. It
never attempts authentication, submission, hidden-test access, or anti-bot
workarounds.
"""

import ast
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Literal, cast
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover - exercised only in minimal installs

    class _CompatResponse:
        def __init__(self, status_code: int, body: bytes):
            self.status_code = status_code
            self._body = body

        def json(self) -> Any:
            return json.loads(self._body.decode("utf-8"))

    class _CompatSession:
        def post(self, url: str, json: Any = None, headers: Any = None, timeout: Any = None) -> Any:
            request = urllib.request.Request(
                url,
                data=__import__("json").dumps(json).encode("utf-8"),
                headers=headers or {},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return _CompatResponse(response.status, response.read())
            except urllib.error.HTTPError as exc:
                return _CompatResponse(exc.code, exc.read())

    class _CompatRequests:
        RequestException = urllib.error.URLError
        HTTPError = urllib.error.HTTPError
        Session = _CompatSession

    requests = _CompatRequests()  # type: ignore[assignment]

from src.importers.base import ImportResult, ProblemImporter
from src.models import Problem
from src.utils.logging import get_logger

logger = get_logger(__name__)


QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    content
    difficulty
    topicTags { name slug }
    exampleTestcases
    codeSnippets { lang langSlug code }
  }
}
"""

PROBLEMSET_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total
    questions {
      questionFrontendId
      titleSlug
      title
      difficulty
      topicTags { name slug }
    }
  }
}
"""

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_BLOCK_TAG_RE = re.compile(r"</?(?:p|div|li|ul|ol|h[1-6]|blockquote|section|tr|table)[^>]*>", re.I)
_ASSIGNMENT_RE = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.*)$", re.S)


class LeetCodeTransientError(RuntimeError):
    """A retryable public endpoint failure."""


class LeetCodeImporter(ProblemImporter):
    """Import public LeetCode question metadata and examples."""

    endpoint = "https://leetcode.com/graphql"
    allowed_hosts = {"leetcode.com", "www.leetcode.com"}

    def __init__(
        self,
        session: Any = None,
        timeout: float = 15.0,
        retries: int = 2,
        backoff_seconds: float = 0.5,
        batch_delay_seconds: float = 0.2,
        sleep: Any = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.batch_delay_seconds = max(0.0, batch_delay_seconds)
        self.sleep = sleep
        self.transform_failures: list[dict[str, Any]] = []

    @classmethod
    def parse_source(cls, source: str) -> tuple[str, str]:
        """Return a validated slug and canonical public URL."""
        value = source.strip()
        if not value:
            raise ValueError("LeetCode URL or slug cannot be empty")
        if "://" not in value:
            slug = value.strip("/").lower()
            if not _SLUG_RE.fullmatch(slug):
                raise ValueError(f"Invalid LeetCode slug: {source}")
            return slug, f"https://leetcode.com/problems/{slug}/"

        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if host not in cls.allowed_hosts:
            raise ValueError(f"Unsupported LeetCode host '{host or 'unknown'}'; use leetcode.com")
        # Split URL path by forward slash (RFC 3986 URL path delimiter, not filesystem separator)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0].lower() != "problems":
            raise ValueError("LeetCode URL must contain /problems/<slug>")
        slug = parts[1].lower()
        if not _SLUG_RE.fullmatch(slug):
            raise ValueError(f"Invalid LeetCode slug: {slug}")
        return slug, f"https://leetcode.com/problems/{slug}/"

    def fetch_problems(
        self,
        source: str | None = None,
        tags: list[str] | None = None,
        difficulty: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch LeetCode questions.

        Single-question mode (when source is provided):
            Fetch one question by URL or slug. Batch parameters are ignored.

        Batch mode (when source is None and filters are provided):
            Fetch multiple questions matching the given tags/difficulty/limit.

        Args:
            source: LeetCode URL or slug for single-question import
            tags: Filter by tags (batch mode only)
            difficulty: Filter by difficulty: easy, medium, or hard (batch mode only)
            limit: Maximum number of questions to fetch (batch mode only)

        Returns:
            List of raw question data dictionaries
        """
        # Single-question mode: source provided
        if source:
            slug, canonical_url = self.parse_source(source)
            return self._fetch_question_data(slug, canonical_url)

        # Batch mode: no source but filters provided
        if tags or difficulty or limit:
            return self._fetch_batch_questions(tags=tags, difficulty=difficulty, limit=limit)

        # Neither mode: error
        raise ValueError(
            "LeetCode import requires either a source (URL/slug) or batch filters (tags, difficulty, limit)"
        )

    def _fetch_question_data(self, slug: str, canonical_url: str) -> list[dict[str, Any]]:
        """Fetch a single question's full data."""
        payload = {"query": QUESTION_QUERY, "variables": {"titleSlug": slug}}
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://leetcode.com",
            "Referer": canonical_url,
            "User-Agent": "Mozilla/5.0 (compatible; LLM-Algorithm-Harness/0.1)",
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(
                    self.endpoint, json=payload, headers=headers, timeout=self.timeout  # type: ignore[arg-type]
                )
                status = getattr(response, "status_code", 200)
                if status in {401, 403}:
                    raise ValueError("LeetCode denied public access or requires authentication")
                if status == 404:
                    raise ValueError(f"LeetCode question not found: {slug}")
                if status == 429:
                    raise LeetCodeTransientError("LeetCode rate limit exceeded")
                if status >= 500:
                    raise LeetCodeTransientError(f"LeetCode server error: HTTP {status}")
                if status >= 400:
                    raise ValueError(f"LeetCode request failed with HTTP {status}")
                body = response.json()
                if body.get("errors"):
                    messages = "; ".join(
                        str(error.get("message", error)) for error in body["errors"]
                    )
                    raise ValueError(f"LeetCode GraphQL error: {messages}")
                question = (body.get("data") or {}).get("question")
                if not question:
                    raise ValueError(f"LeetCode question not found or is restricted: {slug}")
                question = dict(question)
                question["_source_slug"] = slug
                question["_source_url"] = canonical_url
                return [question]
            except ValueError:
                raise
            except (LeetCodeTransientError, requests.RequestException, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                self.sleep(self.backoff_seconds * (2**attempt))
        raise RuntimeError(
            f"Unable to fetch LeetCode question '{slug}': {last_error}"
        ) from last_error

    def _fetch_question_list(
        self,
        tags: list[str] | None = None,
        difficulty: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch question metadata list using problemsetQuestionList query.

        Returns:
            List of question metadata dicts with keys: questionFrontendId, titleSlug,
            title, difficulty, topicTags
        """
        # Normalize difficulty to LeetCode's enum format
        difficulty_enum = None
        if difficulty:
            difficulty_lower = difficulty.lower()
            if difficulty_lower == "easy":
                difficulty_enum = "EASY"
            elif difficulty_lower == "medium":
                difficulty_enum = "MEDIUM"
            elif difficulty_lower == "hard":
                difficulty_enum = "HARD"
            else:
                raise ValueError(f"Invalid difficulty: {difficulty}. Must be easy, medium, or hard")

        # Build filters
        filters: dict[str, Any] = {}
        if tags:
            filters["tags"] = tags
        if difficulty_enum:
            filters["difficulty"] = difficulty_enum

        variables: dict[str, Any] = {
            "categorySlug": "",
            "skip": 0,
            "limit": limit or 50,
            "filters": filters if filters else {},
        }

        payload = {"query": PROBLEMSET_QUERY, "variables": variables}
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://leetcode.com",
            "Referer": "https://leetcode.com/problemset/",
            "User-Agent": "Mozilla/5.0 (compatible; LLM-Algorithm-Harness/0.1)",
        }

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(
                    self.endpoint, json=payload, headers=headers, timeout=self.timeout  # type: ignore[arg-type]
                )
                status = getattr(response, "status_code", 200)
                if status == 429:
                    raise LeetCodeTransientError("LeetCode rate limit exceeded")
                if status >= 500:
                    raise LeetCodeTransientError(f"LeetCode server error: HTTP {status}")
                if status >= 400:
                    raise ValueError(f"LeetCode request failed with HTTP {status}")

                body = response.json()
                if body.get("errors"):
                    messages = "; ".join(
                        str(error.get("message", error)) for error in body["errors"]
                    )
                    raise ValueError(f"LeetCode GraphQL error: {messages}")

                data = body.get("data", {})
                result = data.get("problemsetQuestionList")
                if not result:
                    raise ValueError("LeetCode problemsetQuestionList returned no data")

                questions: list[dict[str, Any]] = result.get("questions")
                if questions is None:
                    raise ValueError("LeetCode response missing 'questions' field")

                # Validate each question has required fields
                for q in questions:
                    if not q.get("titleSlug"):
                        raise ValueError(f"Question missing titleSlug: {q}")

                return questions

            except ValueError:
                raise
            except (LeetCodeTransientError, requests.RequestException, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                self.sleep(self.backoff_seconds * (2**attempt))

        raise RuntimeError(f"Unable to fetch LeetCode question list: {last_error}") from last_error

    def _fetch_batch_questions(
        self,
        tags: list[str] | None = None,
        difficulty: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch multiple questions in batch mode.

        First fetches the question list, then fetches details for each question.
        Partial failures are recorded but don't stop the batch.
        """
        # Get question list
        question_list = self._fetch_question_list(tags, difficulty, limit)

        if not question_list:
            logger.info("leetcode_batch_no_questions", tags=tags, difficulty=difficulty)
            return []

        total = len(question_list)
        logger.info("leetcode_batch_start", total=total, tags=tags, difficulty=difficulty)

        # Fetch details for each question
        results = []
        for idx, question_meta in enumerate(question_list):
            slug = question_meta["titleSlug"]
            canonical_url = f"https://leetcode.com/problems/{slug}/"

            print(f"Fetching problem {idx+1}/{total}: {slug}")

            try:
                question_data = self._fetch_question_data(slug, canonical_url)
                results.extend(question_data)
            except Exception as exc:
                # Record failure but continue with other questions
                logger.warning(
                    "leetcode_batch_question_failed",
                    slug=slug,
                    index=idx,
                    error=str(exc),
                )
                self.transform_failures.append(
                    {
                        "index": idx,
                        "problem_id": question_meta.get("questionFrontendId", "unknown"),
                        "slug": slug,
                        "error": str(exc),
                    }
                )

            # Add delay between requests to avoid rate limiting
            if idx < total - 1:
                self.sleep(self.batch_delay_seconds)

        logger.info(
            "leetcode_batch_complete",
            total=total,
            fetched=len(results),
            failed=len(self.transform_failures),
        )
        return results

    def transform_to_schema(self, raw_data: Any) -> list[Problem]:
        """Transform GraphQL question data to the project Problem schema."""
        items = raw_data if isinstance(raw_data, list) else [raw_data]
        problems = []
        self.transform_failures = []
        for index, item in enumerate(items):
            try:
                problems.append(self._transform_question(item))
            except Exception as exc:
                self.transform_failures.append(
                    {
                        "index": index,
                        "problem_id": str(item.get("questionFrontendId", "unknown")),
                        "error": str(exc),
                    }
                )
                logger.warning("leetcode_problem_transform_failed", index=index, error=str(exc))
        return problems

    def _transform_question(self, question: dict[str, Any]) -> Problem:
        slug = question.get("_source_slug") or self._slug_from_question(question)
        source_url = question.get("_source_url") or f"https://leetcode.com/problems/{slug}/"
        content = self.clean_html_content(question.get("content") or "")
        notes: list[str] = []
        entry_point = self._extract_entry_point(question.get("codeSnippets") or [])
        if entry_point is None:
            entry_point = "solution(**test_input)"
            notes.append(
                "Python entry signature could not be extracted; review entry_point manually."
            )

        public_cases, sample_notes = self._extract_public_examples(content, entry_point)
        notes.extend(sample_notes)
        needs_manual = bool(notes)
        frontend_id = question.get("questionFrontendId") or question.get("questionId") or slug
        tags = [tag.get("name", "") for tag in question.get("topicTags") or [] if tag.get("name")]
        constraints = self.clean_html_content(question.get("constraints") or "")
        if not constraints:
            constraints = self._extract_constraints(content)

        difficulty_str = str(question.get("difficulty") or "medium").lower()
        difficulty = cast(Literal["easy", "medium", "hard"], difficulty_str)

        from src.models import TestCase

        public_test_cases = [TestCase(**case) for case in public_cases]

        return Problem(
            schema_version="1.1",
            problem_id=f"leetcode-{frontend_id}",
            title=question.get("title") or slug.replace("-", " ").title(),
            description=content or "LeetCode question description requires manual completion.",
            difficulty=difficulty,
            tags=tags,
            constraints=constraints or None,
            source_platform="leetcode",
            source_problem_id=str(frontend_id),
            source_url=source_url,
            source_version="leetcode-graphql-public-v1",
            input_output_mode="function",
            entry_point=entry_point,
            public_test_cases=public_test_cases,
            needs_manual_completion=needs_manual,
            manual_completion_notes=notes,
        )

    @staticmethod
    def _slug_from_question(question: dict[str, Any]) -> str:
        value = str(question.get("titleSlug") or question.get("title") or "leetcode-question")
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    @staticmethod
    def clean_html_content(content: str) -> str:
        """Convert LeetCode HTML to readable text while preserving code/formulas."""
        text = content
        text = re.sub(
            r"<pre[^>]*>\s*(?:<code[^>]*>)?(.*?)</(?:code\s*>)?pre>",
            lambda match: "\n```\n"
            + html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))
            + "\n```\n",
            text,
            flags=re.I | re.S,
        )
        text = re.sub(
            r"<code[^>]*>(.*?)</code>", lambda m: f"`{m.group(1)}`", text, flags=re.I | re.S
        )
        text = re.sub(r"<sup[^>]*>(.*?)</sup>", r"^\1", text, flags=re.I | re.S)
        text = re.sub(r"<sub[^>]*>(.*?)</sub>", r"_\1", text, flags=re.I | re.S)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = _BLOCK_TAG_RE.sub("\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _extract_entry_point(snippets: list[dict[str, Any]]) -> str | None:
        snippet = next(
            (
                item.get("code", "")
                for item in snippets
                if str(item.get("langSlug", "")).lower() in {"python", "python3"}
            ),
            "",
        )
        if not snippet:
            return None
        try:
            tree = ast.parse(snippet)
        except SyntaxError:
            tree = None
        if tree is None:
            class_match = re.search(
                r"class\s+Solution\b.*?def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)",
                snippet,
                flags=re.S,
            )
            if class_match:
                args = LeetCodeImporter._signature_argument_names(
                    class_match.group(2), skip_self=True
                )
                return f"Solution.{class_match.group(1)}({', '.join(args)})"
            function_match = re.search(
                r"^\s*def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", snippet, flags=re.M
            )
            if function_match:
                args = LeetCodeImporter._signature_argument_names(function_match.group(2))
                return f"{function_match.group(1)}({', '.join(args)})"
            return None
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "Solution":
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [arg.arg for arg in child.args.args if arg.arg != "self"]
                        return f"Solution.{child.name}({', '.join(args)})"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                return f"{node.name}({', '.join(args)})"
        return None

    @staticmethod
    def _signature_argument_names(signature: str, skip_self: bool = False) -> list[str]:
        """Extract plain argument names from a Python signature stub."""
        names = []
        for argument in signature.split(","):
            name = argument.strip().split(":", 1)[0].split("=", 1)[0].strip()
            name = name.lstrip("*")
            if name and (not skip_self or name != "self"):
                names.append(name)
        return names

    @classmethod
    def _extract_public_examples(
        cls, content: str, entry_point: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Extract only unambiguous Input/Output pairs from cleaned content."""
        cases: list[dict[str, Any]] = []
        notes: list[str] = []
        pattern = re.compile(r"Input\s*:\s*(.*?)\s+Output\s*:\s*([^\n`]+)", flags=re.I | re.S)
        for match in pattern.finditer(content):
            parsed_input = cls._parse_named_values(match.group(1).strip())
            parsed_output = cls._parse_literal(match.group(2).strip())
            if parsed_input is None or parsed_output is None:
                continue
            cases.append({"input": parsed_input, "expected_output": parsed_output})
        if not cases:
            notes.append(
                "Public Input/Output examples could not be paired reliably; review public_test_cases manually."
            )
        return cases, notes

    @staticmethod
    def _extract_constraints(content: str) -> str:
        """Extract a trailing Constraints section when GraphQL omits the field."""
        match = re.search(
            r"(?:^|\n)\s*Constraints\s*:\s*(.*?)(?=\n\s*(?:Follow up|Related Topics|Similar Questions)\s*:|\Z)",
            content,
            flags=re.I | re.S,
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _parse_literal(value: str) -> Any:
        value = value.strip().strip("`")
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            try:
                import json

                return json.loads(value)
            except (ValueError, TypeError):
                return None

    @classmethod
    def _parse_named_values(cls, value: str) -> dict[str, Any] | None:
        parts = cls._split_top_level(value)
        parsed: dict[str, Any] = {}
        for part in parts:
            match = _ASSIGNMENT_RE.match(part.strip())
            if not match:
                return None
            parsed[match.group(1)] = cls._parse_literal(match.group(2))
            if parsed[match.group(1)] is None:
                return None
        return parsed or None

    @staticmethod
    def _split_top_level(value: str) -> list[str]:
        parts: list[str] = []
        start = 0
        depth = 0
        quote: str | None = None
        escaped = False
        for index, char in enumerate(value):
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in "'\"":
                quote = char
            elif char in "[{(":
                depth += 1
            elif char in "]})":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(value[start:index])
                start = index + 1
        parts.append(value[start:])
        return [part.strip() for part in parts if part.strip()]

    def detect_duplicates(
        self, problems: list[Problem], existing_problems: list[Problem], update_strategy: str
    ) -> tuple[list[Problem], list[str], list[str]]:
        """Reuse the standard source/platform duplicate policy."""
        from src.importers.local_json import LocalJsonImporter

        return LocalJsonImporter().detect_duplicates(problems, existing_problems, update_strategy)

    def generate_report(
        self, result: ImportResult, source: str, output_path: str, preview: bool
    ) -> dict[str, Any]:
        """Generate a source-specific import report."""
        manual = [
            problem.problem_id for problem in result.successful if problem.needs_manual_completion
        ]
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "leetcode",
            "input_path": source,
            "output_path": output_path,
            "preview_mode": preview,
            "summary": {
                "total_attempted": result.total_attempted,
                "successful": len(result.successful),
                "failed": len(result.failed),
                "duplicates_skipped": len(result.duplicates_skipped),
                "duplicates_overwritten": len(result.duplicates_overwritten),
                "needs_manual_completion": len(manual),
            },
            "manual_completion": manual,
            "failed_problems": result.failed,
            "warnings": result.warnings,
        }
