"""
Problem and dataset fingerprint calculation for incremental evaluation.
"""

import hashlib
import json
from typing import Dict

from src.models import Problem


def compute_problem_fingerprint(problem: Problem) -> str:
    """
    Calculate SHA256 fingerprint for a single problem.

    The fingerprint is computed from all fields that affect evaluation:
    - problem_id
    - description
    - test cases (public, feedback, hidden)
    - entry_point
    - judge_config
    - input_output_mode

    Args:
        problem: Problem instance to fingerprint

    Returns:
        SHA256 hex digest of the problem content

    Raises:
        AttributeError: If problem is missing required fields
    """
    # Build a stable JSON representation of all evaluation-relevant fields
    content = {
        "problem_id": problem.problem_id,
        "description": problem.description,
        "input_output_mode": problem.input_output_mode,
        "entry_point": problem.entry_point,
        # Include all test cases
        "public_test_cases": [tc.model_dump() for tc in problem.public_test_cases],
        "feedback_test_cases": [tc.model_dump() for tc in problem.feedback_test_cases],
        "hidden_test_cases": [tc.model_dump() for tc in problem.hidden_test_cases],
        # Include judge configuration
        "judge_config": problem.judge_config.model_dump(),
    }

    # Serialize to stable JSON (sorted keys) and compute hash
    stable_json = json.dumps(content, sort_keys=True)
    return hashlib.sha256(stable_json.encode("utf-8")).hexdigest()


def compute_dataset_fingerprint(problems: list[Problem]) -> Dict[str, str]:
    """
    Generate fingerprint mapping for an entire dataset.

    Args:
        problems: List of Problem instances

    Returns:
        Dict mapping problem_id to its fingerprint

    Example:
        >>> fingerprints = compute_dataset_fingerprint(problems)
        >>> fingerprints
        {'two_sum': 'abc123...', 'reverse_string': 'def456...'}
    """
    return {problem.problem_id: compute_problem_fingerprint(problem) for problem in problems}
