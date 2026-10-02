"""Tests for result merging logic."""

import pytest

from src.incremental.merger import merge_results
from src.models import ExecutionResult


@pytest.fixture
def new_results():
    """Create new evaluation results."""
    return {
        "direct": [
            ExecutionResult(
                problem_id="prob1",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.5,
                source="fresh",
            ),
            ExecutionResult(
                problem_id="prob2",
                strategy="direct",
                generated_code="def solution(): pass",
                status="failure",
                execution_time_seconds=2.0,
                source="fresh",
            ),
        ]
    }


@pytest.fixture
def historical_results():
    """Create historical results."""
    return {
        "direct": [
            ExecutionResult(
                problem_id="prob3",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.0,
                source="reused",
            ),
            ExecutionResult(
                problem_id="prob4",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.2,
                source="reused",
            ),
        ]
    }


def test_merge_results_both_present(new_results, historical_results):
    """Test merging when both new and historical results exist."""
    merged = merge_results(new_results, historical_results)

    assert "direct" in merged
    assert len(merged["direct"]) == 4

    # Check all problem IDs are present
    problem_ids = {r.problem_id for r in merged["direct"]}
    assert problem_ids == {"prob1", "prob2", "prob3", "prob4"}

    # Check sources are preserved
    sources = {r.problem_id: r.source for r in merged["direct"]}
    assert sources["prob1"] == "fresh"
    assert sources["prob2"] == "fresh"
    assert sources["prob3"] == "reused"
    assert sources["prob4"] == "reused"


def test_merge_results_only_new(new_results):
    """Test merging with only new results."""
    merged = merge_results(new_results, {})

    assert "direct" in merged
    assert len(merged["direct"]) == 2
    assert all(r.source == "fresh" for r in merged["direct"])


def test_merge_results_only_historical(historical_results):
    """Test merging with only historical results."""
    merged = merge_results({}, historical_results)

    assert "direct" in merged
    assert len(merged["direct"]) == 2
    assert all(r.source == "reused" for r in merged["direct"])


def test_merge_results_empty():
    """Test merging with no results."""
    merged = merge_results({}, {})
    assert merged == {}


def test_merge_results_multiple_strategies():
    """Test merging with multiple strategies."""
    new_results = {
        "direct": [
            ExecutionResult(
                problem_id="prob1",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.0,
            )
        ],
        "cot": [
            ExecutionResult(
                problem_id="prob1",
                strategy="cot",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=2.0,
            )
        ],
    }

    historical_results = {
        "direct": [
            ExecutionResult(
                problem_id="prob2",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.0,
                source="reused",
            )
        ],
        "cot": [
            ExecutionResult(
                problem_id="prob2",
                strategy="cot",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=2.0,
                source="reused",
            )
        ],
    }

    merged = merge_results(new_results, historical_results)

    assert "direct" in merged
    assert "cot" in merged
    assert len(merged["direct"]) == 2
    assert len(merged["cot"]) == 2


def test_merge_results_preserves_order():
    """Test that merge preserves problem order."""
    new_results = {
        "direct": [
            ExecutionResult(
                problem_id="prob1",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.0,
            ),
            ExecutionResult(
                problem_id="prob3",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.0,
            ),
        ]
    }

    historical_results = {
        "direct": [
            ExecutionResult(
                problem_id="prob2",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.0,
                source="reused",
            )
        ]
    }

    merged = merge_results(new_results, historical_results)

    # New results should come first, then historical
    problem_ids = [r.problem_id for r in merged["direct"]]
    assert problem_ids[:2] == ["prob1", "prob3"]
    assert problem_ids[2:] == ["prob2"]


def test_merge_results_source_defaults():
    """Test that source field defaults to 'fresh' for new results."""
    new_results = {
        "direct": [
            ExecutionResult(
                problem_id="prob1",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                execution_time_seconds=1.0,
                # source not explicitly set, uses default
            )
        ]
    }

    merged = merge_results(new_results, {})

    # Source should default to "fresh"
    assert merged["direct"][0].source == "fresh"
