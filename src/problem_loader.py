"""
Problem Loader - Load and validate algorithm problem datasets.
"""

import json
from pathlib import Path
from typing import List, Optional

from pydantic import ValidationError

from src.models import Problem
from src.utils.logging import get_logger
from src.utils.validators import validate_problem_schema

logger = get_logger(__name__)


class ProblemLoader:
    """Problem dataset loader."""

    def load(self, dataset_path: str) -> List[Problem]:
        """
        Load problems from JSON file.

        Args:
            dataset_path: Path to dataset JSON file

        Returns:
            List of Problem objects

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If JSON is malformed
            ValueError: If dataset is empty
        """
        path = Path(dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

        logger.info("loading_dataset", path=dataset_path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("Dataset must be a JSON array")

        if len(data) == 0:
            raise ValueError("Dataset is empty")

        problems = self.validate_dataset(data)

        logger.info("dataset_loaded", total_problems=len(problems), path=dataset_path)

        return problems

    def validate_dataset(self, data: List[dict]) -> List[Problem]:
        """
        Validate and convert dataset to Problem objects.

        Args:
            data: Raw dataset (list of dicts)

        Returns:
            List of validated Problem objects

        Raises:
            ValidationError: If validation fails
        """
        problems = []
        errors = []

        for i, item in enumerate(data):
            try:
                # Validate schema
                validate_problem_schema(item)

                # Create Problem object (Pydantic validation)
                problem = Problem(**item)
                problems.append(problem)

            except (ValueError, ValidationError) as e:
                error_msg = f"Problem at index {i} (id: {item.get('problem_id', 'unknown')}): {e}"
                errors.append(error_msg)
                logger.warning("problem_validation_failed", index=i, error=str(e))

        if errors:
            logger.warning(
                "dataset_validation_completed",
                total=len(data),
                valid=len(problems),
                invalid=len(errors),
            )

        # If all problems failed validation, raise error
        if len(problems) == 0:
            raise ValueError(f"All problems failed validation:\n" + "\n".join(errors))

        return problems

    def filter_problems(
        self,
        problems: List[Problem],
        difficulty: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Problem]:
        """
        Filter problems by criteria.

        Args:
            problems: Problem list
            difficulty: Filter by difficulty (optional)
            tags: Filter by tags (any match, optional)
            limit: Maximum number to return (optional)

        Returns:
            Filtered problem list
        """
        filtered = problems

        # Filter by difficulty
        if difficulty:
            filtered = [p for p in filtered if p.difficulty == difficulty]
            logger.info("filtered_by_difficulty", difficulty=difficulty, count=len(filtered))

        # Filter by tags
        if tags:
            filtered = [p for p in filtered if any(tag in p.tags for tag in tags)]
            logger.info("filtered_by_tags", tags=tags, count=len(filtered))

        # Apply limit
        if limit and limit > 0:
            filtered = filtered[:limit]
            logger.info("applied_limit", limit=limit, count=len(filtered))

        return filtered

    def load_from_dict(self, data: dict) -> Problem:
        """
        Load a single problem from dictionary.

        Args:
            data: Problem data dictionary

        Returns:
            Problem object

        Raises:
            ValidationError: If validation fails
        """
        validate_problem_schema(data)
        return Problem(**data)
