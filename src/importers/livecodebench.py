"""Safe importer for versioned LiveCodeBench JSON/JSONL caches."""

import ast
import hashlib
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.importers.base import ImportResult, ProblemImporter
from src.models import Problem
from src.utils.logging import get_logger

logger = get_logger(__name__)


class LiveCodeBenchImporter(ProblemImporter):
    """Import a pinned LiveCodeBench release without unsafe deserialization."""

    SUPPORTED_RELEASES = {f"release_v{index}" for index in range(1, 7)}

    def __init__(
        self,
        release_version: str = "release_v6",
        start_date: str | None = None,
        end_date: str | None = None,
        difficulty: str | None = None,
        limit: int | None = None,
        timeout: float = 30.0,
    ):
        if release_version not in self.SUPPORTED_RELEASES:
            supported = ", ".join(sorted(self.SUPPORTED_RELEASES))
            raise ValueError(f"Unsupported LiveCodeBench release '{release_version}'. Use: {supported}")
        self.release_version = release_version
        self.start_date = start_date
        self.end_date = end_date
        self.difficulty = difficulty.lower() if difficulty else None
        self.limit = limit
        self.timeout = timeout
        self.source_digest: str | None = None
        self.selected_problem_ids: List[str] = []
        self.transform_failures: List[Dict[str, Any]] = []

    def fetch_problems(self, source: str) -> Any:
        """Read a local JSON/JSONL cache or a static JSON/JSONL URL."""
        if source.startswith("http://") or source.startswith("https://"):
            request = urllib.request.Request(
                source,
                headers={"User-Agent": "LLM-Algorithm-Harness/0.1"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw_bytes = response.read()
        else:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"LiveCodeBench cache not found: {source}")
            raw_bytes = path.read_bytes()

        self.source_digest = hashlib.sha256(raw_bytes).hexdigest()
        text = raw_bytes.decode("utf-8")
        if source.lower().endswith(".jsonl"):
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("LiveCodeBench cache must be a JSON array or JSONL file")
        return data

    def transform_to_schema(self, raw_data: Any) -> List[Problem]:
        """Transform safe JSON records into Problem objects with filters applied."""
        if not isinstance(raw_data, list):
            raise ValueError("LiveCodeBench data must be a list")
        self.transform_failures = []
        self.selected_problem_ids = []
        problems: List[Problem] = []
        for index, record in enumerate(raw_data):
            try:
                if not isinstance(record, dict) or not self._matches_filters(record):
                    continue
                problem = self._transform_record(record)
                problems.append(problem)
                self.selected_problem_ids.append(problem.problem_id)
            except Exception as exc:
                self.transform_failures.append(
                    {
                        "index": index,
                        "problem_id": str(record.get("question_id", "unknown"))
                        if isinstance(record, dict)
                        else "unknown",
                        "error": str(exc),
                    }
                )
        if self.limit is not None:
            problems = problems[: self.limit]
            self.selected_problem_ids = [problem.problem_id for problem in problems]
        return problems

    def _matches_filters(self, record: Dict[str, Any]) -> bool:
        difficulty = str(record.get("difficulty", "")).lower()
        if self.difficulty and difficulty != self.difficulty:
            return False
        contest_date = str(record.get("contest_date", ""))[:10]
        if self.start_date and contest_date and contest_date < self.start_date:
            return False
        if self.end_date and contest_date and contest_date > self.end_date:
            return False
        return True

    def _transform_record(self, record: Dict[str, Any]) -> Problem:
        metadata = self._safe_json(record.get("metadata"), default={})
        public_raw, public_note = self._decode_tests(record.get("public_test_cases"))
        private_raw, private_note = self._decode_tests(record.get("private_test_cases"))
        notes = [note for note in (public_note, private_note) if note]
        public_cases, public_mode = self._map_tests(public_raw, "public", notes)
        hidden_cases, hidden_mode = self._map_tests(private_raw, "hidden", notes)
        modes = {mode for mode in (public_mode, hidden_mode) if mode}
        if len(modes) > 1:
            notes.append("Public and hidden tests use different protocols; review input_output_mode manually.")
        input_output_mode = next(iter(modes), "function")
        entry_point = self._entry_point(record, metadata, input_output_mode)
        if not entry_point:
            entry_point = "main()" if input_output_mode == "stdin_stdout" else "solution(**test_input)"
            notes.append("Entry point could not be extracted; review entry_point manually.")
        question_id = str(record.get("question_id") or record.get("id") or "unknown")
        contest_date = str(record.get("contest_date") or "")
        source_metadata = {
            "contest_id": record.get("contest_id"),
            "contest_date": contest_date,
            "release_version": self.release_version,
            "content_sha256": self.source_digest,
            "filters": {
                "start_date": self.start_date,
                "end_date": self.end_date,
                "difficulty": self.difficulty,
                "limit": self.limit,
            },
        }
        return Problem(
            schema_version="1.1",
            problem_id=f"livecodebench-{question_id}",
            title=str(record.get("question_title") or question_id),
            description=str(record.get("question_content") or "LiveCodeBench question requires manual completion."),
            difficulty=str(record.get("difficulty") or "medium").lower(),
            tags=[],
            source_platform="livecodebench",
            source_problem_id=question_id,
            source_version=self.release_version,
            source_metadata=source_metadata,
            input_output_mode=input_output_mode,
            entry_point=entry_point,
            public_test_cases=public_cases,
            hidden_test_cases=hidden_cases,
            needs_manual_completion=bool(notes or not public_cases),
            manual_completion_notes=notes,
        )

    @staticmethod
    def _safe_json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return default

    @classmethod
    def _decode_tests(cls, value: Any) -> Tuple[List[Dict[str, Any]], str | None]:
        """Decode JSON tests only; never execute pickle/zlib payloads."""
        if value is None:
            return [], None
        if isinstance(value, list):
            return value, None
        if not isinstance(value, str):
            return [], "Test payload has an unsupported type; manual completion required."
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [], "Test payload is not JSON; compressed/pickle decoding is intentionally disabled."
        if not isinstance(decoded, list):
            return [], "Test payload JSON is not a list; manual completion required."
        return decoded, None

    @classmethod
    def _map_tests(
        cls, records: List[Dict[str, Any]], source: str, notes: List[str]
    ) -> Tuple[List[Dict[str, Any]], str | None]:
        mapped: List[Dict[str, Any]] = []
        modes = set()
        for record in records:
            if not isinstance(record, dict) or "input" not in record or "output" not in record:
                notes.append(f"A {source} test lacks input/output fields; manual completion required.")
                continue
            test_type = str(record.get("testtype", "functional")).lower()
            if test_type == "stdin":
                mode = "stdin_stdout"
                input_value = record["input"]
                output_value = record["output"]
            elif test_type == "functional":
                mode = "function"
                input_value = cls._parse_value(record["input"])
                output_value = cls._parse_value(record["output"])
                if input_value is None or output_value is None:
                    notes.append(f"A {source} functional test is not safe JSON; manual completion required.")
                    continue
            else:
                notes.append(f"Unsupported LiveCodeBench test type '{test_type}'; manual completion required.")
                continue
            modes.add(mode)
            mapped.append({"input": input_value, "expected_output": output_value})
        return mapped, next(iter(modes), None)

    @staticmethod
    def _parse_value(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return None

    @staticmethod
    def _entry_point(record: Dict[str, Any], metadata: Dict[str, Any], mode: str) -> str | None:
        if mode == "stdin_stdout":
            return "main()"
        function_name = metadata.get("func_name") or metadata.get("function_name")
        starter = str(record.get("starter_code") or "")
        if function_name:
            return f"{function_name}(**test_input)"
        match = re.search(r"(?:def|function)\s+([A-Za-z_]\w*)\s*\(", starter)
        return f"{match.group(1)}(**test_input)" if match else None

    def detect_duplicates(self, problems, existing_problems, update_strategy):
        from src.importers.local_json import LocalJsonImporter

        return LocalJsonImporter().detect_duplicates(problems, existing_problems, update_strategy)

    def generate_report(self, result: ImportResult, source: str, output_path: str, preview: bool):
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "livecodebench",
            "input_path": source,
            "output_path": output_path,
            "preview_mode": preview,
            "release_version": self.release_version,
            "filters": {
                "start_date": self.start_date,
                "end_date": self.end_date,
                "difficulty": self.difficulty,
                "limit": self.limit,
            },
            "selected_problem_ids": list(self.selected_problem_ids),
            "source_sha256": self.source_digest,
            "summary": {
                "total_attempted": result.total_attempted,
                "successful": len(result.successful),
                "failed": len(result.failed),
                "duplicates_skipped": len(result.duplicates_skipped),
                "duplicates_overwritten": len(result.duplicates_overwritten),
            },
            "failed_problems": result.failed,
            "warnings": result.warnings,
        }
