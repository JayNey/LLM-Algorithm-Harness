"""
Problem Importer - Base class for extensible problem dataset importers.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from src.models import Problem
from src.utils.logging import get_logger
from src.utils.validators import validate_problem_schema

logger = get_logger(__name__)


@dataclass
class ImportResult:
    """Result of an import operation."""

    successful: List[Problem] = field(default_factory=list)
    failed: List[Dict[str, Any]] = field(default_factory=list)
    duplicates_skipped: List[str] = field(default_factory=list)
    duplicates_overwritten: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def total_attempted(self) -> int:
        """Total number of problems attempted to import."""
        return len(self.successful) + len(self.failed)

    @property
    def has_failures(self) -> bool:
        """Whether any problems failed to import."""
        return len(self.failed) > 0

    @property
    def all_failed(self) -> bool:
        """Whether all problems failed to import."""
        return len(self.successful) == 0 and len(self.failed) > 0


class ProblemImporter(ABC):
    """
    Abstract base class for problem dataset importers.

    All platform-specific importers (LocalJson, LeetCode, etc.) must inherit
    from this class and implement the abstract methods.
    """

    @abstractmethod
    def fetch_problems(self, source: str) -> Any:
        """
        Fetch or read raw problem data from the source.

        Args:
            source: Source identifier (file path, URL, etc.)

        Returns:
            Raw data in source-specific format

        Raises:
            FileNotFoundError: If source doesn't exist
            IOError: If source cannot be read
        """
        pass

    @abstractmethod
    def transform_to_schema(self, raw_data: Any) -> List[Problem]:
        """
        Transform raw data to Problem objects.

        Args:
            raw_data: Raw data from fetch_problems()

        Returns:
            List of Problem objects

        Raises:
            ValueError: If transformation fails
        """
        pass

    @abstractmethod
    def detect_duplicates(
        self, problems: List[Problem], existing_problems: List[Problem], update_strategy: str
    ) -> Tuple[List[Problem], List[str], List[str]]:
        """
        Detect and handle duplicate problems.

        Args:
            problems: New problems to import
            existing_problems: Existing problems in dataset
            update_strategy: 'skip' or 'overwrite'

        Returns:
            Tuple of (final_problems, skipped_ids, overwritten_ids)
        """
        pass

    @abstractmethod
    def generate_report(
        self, result: ImportResult, source: str, output_path: str, preview: bool
    ) -> Dict[str, Any]:
        """
        Generate import report.

        Args:
            result: Import result object
            source: Source identifier
            output_path: Output dataset path
            preview: Whether this was a preview run

        Returns:
            Report dictionary
        """
        pass

    def validate_problems(self, problems: List[Problem]) -> Tuple[List[Problem], List[Dict[str, Any]]]:
        """
        Validate problems using schema validation.

        Args:
            problems: List of Problem objects to validate

        Returns:
            Tuple of (valid_problems, failed_items)
        """
        valid = []
        failed = []

        for i, problem in enumerate(problems):
            try:
                # Validate schema
                validate_problem_schema(problem.model_dump())
                # Validate completeness
                if not problem.validate_completeness():
                    raise ValueError("Problem data incomplete")
                valid.append(problem)
            except (ValueError, ValidationError) as e:
                failed.append({
                    "index": i,
                    "problem_id": problem.problem_id if hasattr(problem, "problem_id") else "unknown",
                    "error": str(e),
                })
                logger.warning("problem_validation_failed", index=i, problem_id=problem.problem_id, error=str(e))

        return valid, failed

    def persist_dataset(self, problems: List[Problem], target_path: str) -> None:
        """
        Atomically write dataset to disk.

        Uses temporary file + atomic rename to ensure data integrity.

        Args:
            target_path: Target file path

        Raises:
            IOError: If write fails
        """
        target = Path(target_path)
        temp_path = target.with_suffix(target.suffix + ".tmp")

        try:
            # Ensure parent directory exists
            target.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file
            with open(temp_path, "w", encoding="utf-8") as f:
                data = [p.model_dump(mode="json") for p in problems]
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")  # Trailing newline

            # Atomic rename
            os.rename(temp_path, target)
            logger.info("dataset_persisted", path=target_path, count=len(problems))

        except Exception as e:
            # Clean up temporary file on failure
            if temp_path.exists():
                temp_path.unlink()
            logger.error("dataset_persist_failed", path=target_path, error=str(e))
            raise IOError(f"Failed to write dataset to {target_path}: {e}") from e
