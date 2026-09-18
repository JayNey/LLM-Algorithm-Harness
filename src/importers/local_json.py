"""
Local JSON file importer.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from src.importers.base import ImportResult, ProblemImporter
from src.models import Problem
from src.utils.logging import get_logger

logger = get_logger(__name__)


class LocalJsonImporter(ProblemImporter):
    """
    Importer for local JSON problem files.

    Supports importing problems from JSON files in the standard Problem schema format.
    """

    def fetch_problems(self, source: str) -> Any:
        """
        Read JSON file from local filesystem.

        Args:
            source: Path to JSON file

        Returns:
            Parsed JSON data

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If JSON is malformed
        """
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {source}")

        logger.info("fetching_problems", source=source, source_type="local-json")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("JSON file must contain an array of problems")

        logger.info("problems_fetched", count=len(data), source=source)
        return data

    def transform_to_schema(self, raw_data: Any) -> List[Problem]:
        """
        Transform raw JSON data to Problem objects.

        Handles partial success: invalid problems are skipped, not blocking others.

        Args:
            raw_data: List of problem dictionaries

        Returns:
            List of valid Problem objects
        """
        if not isinstance(raw_data, list):
            raise ValueError("Raw data must be a list")

        problems = []
        for i, item in enumerate(raw_data):
            try:
                # Create Problem object (Pydantic validation)
                problem = Problem(**item)
                problems.append(problem)
            except (ValueError, ValidationError) as e:
                # Log but don't fail - handled in validate_problems
                logger.debug("problem_transform_skipped", index=i, error=str(e))

        logger.info("problems_transformed", total=len(raw_data), successful=len(problems))
        return problems

    def detect_duplicates(
        self, problems: List[Problem], existing_problems: List[Problem], update_strategy: str
    ) -> Tuple[List[Problem], List[str], List[str]]:
        """
        Detect and handle duplicates based on (source_platform, source_problem_id).

        Args:
            problems: New problems to import
            existing_problems: Existing problems in dataset
            update_strategy: 'skip' or 'overwrite'

        Returns:
            Tuple of (final_problems, skipped_ids, overwritten_ids)
        """
        # Build existing problems map: (platform, id) -> Problem
        existing_map: Dict[Tuple[str, str], Problem] = {}
        for p in existing_problems:
            key = (p.source_platform, p.source_problem_id or p.problem_id)
            existing_map[key] = p

        final_problems = list(existing_problems)  # Start with all existing
        skipped_ids = []
        overwritten_ids = []

        for problem in problems:
            key = (problem.source_platform, problem.source_problem_id or problem.problem_id)

            if key in existing_map:
                # Duplicate detected
                if update_strategy == "overwrite":
                    # Remove old, add new
                    old_problem = existing_map[key]
                    final_problems.remove(old_problem)
                    final_problems.append(problem)
                    overwritten_ids.append(problem.problem_id)
                    logger.info("problem_overwritten", problem_id=problem.problem_id)
                else:  # skip
                    skipped_ids.append(problem.problem_id)
                    logger.info("problem_skipped_duplicate", problem_id=problem.problem_id)
            else:
                # New problem
                final_problems.append(problem)

        logger.info(
            "duplicates_detected",
            skipped=len(skipped_ids),
            overwritten=len(overwritten_ids),
            strategy=update_strategy,
        )

        return final_problems, skipped_ids, overwritten_ids

    def generate_report(
        self, result: ImportResult, source: str, output_path: str, preview: bool
    ) -> Dict[str, Any]:
        """
        Generate import report.

        Args:
            result: Import result object
            source: Source file path
            output_path: Output dataset path
            preview: Whether this was a preview run

        Returns:
            Report dictionary
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "source": "local-json",
            "input_path": source,
            "output_path": output_path,
            "preview_mode": preview,
            "summary": {
                "total_attempted": result.total_attempted,
                "successful": len(result.successful),
                "failed": len(result.failed),
                "duplicates_skipped": len(result.duplicates_skipped),
                "duplicates_overwritten": len(result.duplicates_overwritten),
            },
            "successful_problems": [p.problem_id for p in result.successful],
            "failed_problems": result.failed,
            "duplicates": [
                {"problem_id": pid, "action": "skipped"} for pid in result.duplicates_skipped
            ]
            + [
                {"problem_id": pid, "action": "overwritten"}
                for pid in result.duplicates_overwritten
            ],
            "warnings": result.warnings,
        }

        return report
