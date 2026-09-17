"""
Validation utilities for data validation.
"""

from pathlib import Path
from typing import Any, Dict


def validate_problem_schema(data: Dict[str, Any]) -> bool:
    """
    Validate problem data schema.

    Args:
        data: Problem data dictionary

    Returns:
        True if valid

    Raises:
        ValueError: If schema is invalid
    """
    required_fields = ["problem_id", "title", "description", "difficulty"]

    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    if data["difficulty"] not in ["easy", "medium", "hard"]:
        raise ValueError(f"Invalid difficulty: {data['difficulty']}")

    if "test_cases" in data:
        if not isinstance(data["test_cases"], list) or len(data["test_cases"]) == 0:
            raise ValueError("test_cases must be a non-empty list")
    else:
        staged_fields = [
            "public_test_cases",
            "feedback_test_cases",
            "hidden_test_cases",
        ]
        present_fields = [field for field in staged_fields if field in data]
        if not present_fields:
            raise ValueError("Missing required field: test_cases")
        if any(not isinstance(data[field], list) for field in present_fields):
            raise ValueError("Staged test case fields must be lists")
        if not any(data[field] for field in present_fields):
            raise ValueError("At least one staged test case is required")

    return True


def validate_test_case(
    test_case: Dict[str, Any], input_output_mode: str = "function"
) -> bool:
    """
    Validate test case format.

    Args:
        test_case: Test case dictionary

    Returns:
        True if valid

    Raises:
        ValueError: If format is invalid
    """
    if "input" not in test_case:
        raise ValueError("Test case missing 'input' field")

    if "expected_output" not in test_case:
        raise ValueError("Test case missing 'expected_output' field")

    if input_output_mode == "stdin_stdout":
        if not isinstance(test_case["input"], (str, bytes, dict, list, tuple)):
            raise ValueError(
                "Test case 'input' must be raw text or a JSON-serializable value"
            )
    elif not isinstance(test_case["input"], dict):
        raise ValueError("Test case 'input' must be a dictionary")

    return True


def validate_file_path(path: str, must_exist: bool = True) -> bool:
    """
    Validate file path.

    Args:
        path: File path to validate
        must_exist: Whether file must exist

    Returns:
        True if valid

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist and must_exist=True
    """
    if not path:
        raise ValueError("Path cannot be empty")

    path_obj = Path(path)

    if must_exist and not path_obj.exists():
        raise FileNotFoundError(f"File not found: {path}")

    return True


def validate_strategy_name(name: str) -> bool:
    """
    Validate strategy name format.

    Args:
        name: Strategy name

    Returns:
        True if valid

    Raises:
        ValueError: If name is invalid
    """
    if not name:
        raise ValueError("Strategy name cannot be empty")

    if not name.replace("_", "").replace("-", "").isalnum():
        raise ValueError(
            f"Strategy name must be alphanumeric with underscores/hyphens: {name}"
        )

    return True
