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
    """Source and import notes do not affect an already normalized problem."""
    fp1 = compute_problem_fingerprint(sample_problem)

    sample_problem.schema_version = "1.2"
    sample_problem.source_platform = "manual"
    sample_problem.source_problem_id = "p1"
    sample_problem.source_url = "https://example.com/p1"
    sample_problem.source_version = "v2"
    sample_problem.source_metadata = {"reviewed": True}
    sample_problem.needs_manual_completion = True
    sample_problem.manual_completion_notes = ["Check original source"]
    fp2 = compute_problem_fingerprint(sample_problem)

    assert fp1 == fp2


def test_compute_problem_fingerprint_changes_on_judge_config(sample_problem):
    """Test that fingerprint changes when judge config changes."""
    fp1 = compute_problem_fingerprint(sample_problem)

    # Modify judge config
    sample_problem.judge_config.float_tolerance = 1e-9
    fp2 = compute_problem_fingerprint(sample_problem)

    assert fp1 != fp2


def test_compute_problem_fingerprint_invalidates_pre_v2_judge_history(sample_problem):
    # Fingerprint of this unchanged problem before the judge contract was versioned.
    legacy_fingerprint = "787e739f20c3e6031a12011f7306c045e046e5e5d85ffe6f1b1bde303b4f72b2"

    assert compute_problem_fingerprint(sample_problem) != legacy_fingerprint


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
