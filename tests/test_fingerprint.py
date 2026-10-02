"""Tests for problem and dataset fingerprint calculation."""

import pytest

from src.incremental.fingerprint import (
    compute_dataset_fingerprint,
    compute_problem_fingerprint,
)
from src.models import JudgeConfig, Problem, TestCase


@pytest.fixture
def sample_problem():
    """Create a sample problem for testing."""
    return Problem(
        problem_id="test_problem",
        title="Test Problem",
        description="A test problem",
        difficulty="medium",
        tags=["test"],
        constraints="1 <= n <= 100",
        source_platform="test",
        source_problem_id="test_1",
        source_url="https://test.com/1",
        source_version="1.0",
        source_metadata={},
        input_output_mode="function",
        entry_point="solution",
        judge_config=JudgeConfig(),
        public_test_cases=[
            TestCase(input='{"nums": [1, 2]}', expected_output="3", source="public")
        ],
        feedback_test_cases=[],
        hidden_test_cases=[],
    )


def test_compute_problem_fingerprint_stable(sample_problem):
    """Test that fingerprint is stable for the same problem."""
    fp1 = compute_problem_fingerprint(sample_problem)
    fp2 = compute_problem_fingerprint(sample_problem)

    assert fp1 == fp2
    assert len(fp1) == 64  # SHA256 hex digest length


def test_compute_problem_fingerprint_changes_on_description(sample_problem):
    """Test that fingerprint changes when description changes."""
    fp1 = compute_problem_fingerprint(sample_problem)

    # Modify description
    sample_problem.description = "Modified description"
    fp2 = compute_problem_fingerprint(sample_problem)

    assert fp1 != fp2


def test_compute_problem_fingerprint_changes_on_test_case(sample_problem):
    """Test that fingerprint changes when test case changes."""
    fp1 = compute_problem_fingerprint(sample_problem)

    # Modify test case
    sample_problem.public_test_cases[0].expected_output = "4"
    fp2 = compute_problem_fingerprint(sample_problem)

    assert fp1 != fp2


def test_compute_problem_fingerprint_ignores_metadata(sample_problem):
    """Test that fingerprint ignores non-evaluation fields like title, tags."""
    fp1 = compute_problem_fingerprint(sample_problem)

    # Modify non-evaluation fields
    sample_problem.title = "Modified Title"
    sample_problem.tags = ["different", "tags"]
    sample_problem.difficulty = "hard"
    fp2 = compute_problem_fingerprint(sample_problem)

    # Fingerprint should be unchanged
    assert fp1 == fp2


def test_compute_problem_fingerprint_changes_on_judge_config(sample_problem):
    """Test that fingerprint changes when judge config changes."""
    fp1 = compute_problem_fingerprint(sample_problem)

    # Modify judge config
    sample_problem.judge_config.float_tolerance = 1e-9
    fp2 = compute_problem_fingerprint(sample_problem)

    assert fp1 != fp2


def test_compute_dataset_fingerprint():
    """Test dataset fingerprint generation."""
    problems = [
        Problem(
            problem_id="prob1",
            title="Problem 1",
            description="First problem",
            difficulty="easy",
            tags=[],
            constraints="1 <= n <= 100",
            source_platform="test",
            source_problem_id="1",
            source_url="https://test.com/1",
            source_version="1.0",
            source_metadata={},
            input_output_mode="function",
            entry_point="solution",
            judge_config=JudgeConfig(),
            public_test_cases=[TestCase(input='{"n": 1}', expected_output="1", source="public")],
            feedback_test_cases=[],
            hidden_test_cases=[],
        ),
        Problem(
            problem_id="prob2",
            title="Problem 2",
            description="Second problem",
            difficulty="medium",
            tags=[],
            constraints="1 <= n <= 1000",
            source_platform="test",
            source_problem_id="2",
            source_url="https://test.com/2",
            source_version="1.0",
            source_metadata={},
            input_output_mode="function",
            entry_point="solution",
            judge_config=JudgeConfig(),
            public_test_cases=[TestCase(input='{"n": 2}', expected_output="2", source="public")],
            feedback_test_cases=[],
            hidden_test_cases=[],
        ),
    ]

    fingerprints = compute_dataset_fingerprint(problems)

    assert len(fingerprints) == 2
    assert "prob1" in fingerprints
    assert "prob2" in fingerprints
    assert len(fingerprints["prob1"]) == 64
    assert len(fingerprints["prob2"]) == 64
    assert fingerprints["prob1"] != fingerprints["prob2"]


def test_compute_dataset_fingerprint_empty():
    """Test dataset fingerprint with empty list."""
    fingerprints = compute_dataset_fingerprint([])
    assert fingerprints == {}
