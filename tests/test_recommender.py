"""Tests for historical weakness analysis and problem recommendation."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.recommender import RecommendationEngine


def _dataset(tmp_path):
    data = [
        {
            "problem_id": "seen-dp",
            "title": "Seen DP",
            "description": "Dynamic programming problem.",
            "difficulty": "hard",
            "tags": ["dp", "array"],
            "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
        },
        {
            "problem_id": "candidate-dp",
            "title": "Candidate DP",
            "description": "Another dynamic programming problem.",
            "difficulty": "hard",
            "tags": ["dp", "array"],
            "test_cases": [{"input": {"x": 2}, "expected_output": 2}],
        },
        {
            "problem_id": "candidate-graph",
            "title": "Candidate Graph",
            "description": "A graph problem.",
            "difficulty": "medium",
            "tags": ["graph"],
            "test_cases": [{"input": {"x": 3}, "expected_output": 3}],
        },
    ]
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _history(tmp_path):
    history = tmp_path / "results" / "run-1"
    history.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "problem_id": "seen-dp",
            "status": "failed",
            "failure_category": "wrong_answer",
            "hidden_result": {"all_passed": False},
        },
        {
            "problem_id": "seen-dp",
            "status": "failed",
            "failure_category": "wrong_answer",
            "hidden_result": {"all_passed": False},
        },
        {
            "problem_id": "candidate-graph",
            "status": "success",
            "hidden_result": None,
        },
    ]
    (history / "vanilla_results.json").write_text(json.dumps(records), encoding="utf-8")
    (history / "metadata.json").write_text(
        json.dumps({"dataset_path": str(tmp_path / "problems.json")}), encoding="utf-8"
    )
    return tmp_path / "results"


def test_analyze_ranks_weak_groups_and_excludes_seen_problems(tmp_path):
    engine = RecommendationEngine(_history(tmp_path), dataset_path=_dataset(tmp_path))
    report = engine.analyze()

    assert report["history_record_count"] == 3
    assert report["evaluated_problem_count"] == 2
    assert report["weakness_report"][0]["failure_rate"] == 1.0
    assert report["recommended_problem_ids"] == ["candidate-dp"]
    assert (
        "candidate-dp" in report["recommended_problems"][0]["recommendation_reason"]
        or "dp" in report["recommended_problems"][0]["recommendation_reason"]
    )
    assert "seen-dp" not in report["recommended_problem_ids"]


def test_write_outputs_report_and_usable_dataset(tmp_path):
    engine = RecommendationEngine(_history(tmp_path), dataset_path=_dataset(tmp_path))
    output = tmp_path / "recommended.json"
    report = engine.write(output, limit=1)

    assert output.exists()
    dataset_output = tmp_path / "recommended.problems.json"
    assert dataset_output.exists()
    assert json.loads(dataset_output.read_text())[0]["problem_id"] == "candidate-dp"
    saved = json.loads(output.read_text())
    assert saved["recommendation_config"]["dataset_path"] == str(dataset_output)
    assert report["recommended_problem_ids"] == ["candidate-dp"]


def test_threshold_and_min_samples_prevent_weak_group_noise(tmp_path):
    with pytest.raises(ValueError):
        RecommendationEngine(
            _history(tmp_path), dataset_path=_dataset(tmp_path), failure_threshold=0
        )
    engine = RecommendationEngine(
        _history(tmp_path), dataset_path=_dataset(tmp_path), min_samples=3
    )
    assert engine.analyze()["weakness_report"] == []
    assert engine.analyze()["recommended_problem_ids"] == []


def test_dataset_is_inferred_from_metadata(tmp_path):
    dataset = _dataset(tmp_path)
    engine = RecommendationEngine(_history(tmp_path))
    assert engine.dataset_path == dataset


def test_recommend_cli_writes_outputs(tmp_path):
    dataset = _dataset(tmp_path)
    history = _history(tmp_path)
    output = tmp_path / "cli-recommended.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.main",
            "recommend",
            "--history",
            str(history),
            "--dataset",
            str(dataset),
            "--output",
            str(output),
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert completed.returncode == 0, completed.stderr
    assert output.exists()
    assert output.with_name("cli-recommended.problems.json").exists()


def _trace_record(problem_id, status="success", cost="0.5"):
    payload = {
        "problem_id": problem_id,
        "status": status,
        "hidden_result": {"all_passed": status == "success"},
        "iterations": [{}],
    }
    if cost is not None:
        payload["llm_traces"] = [
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "pricing_metadata": {"total_cost": cost, "usage_known": True},
            }
        ]
    return payload


def _gradient_dataset(tmp_path):
    data = [
        {
            "problem_id": "fail-hard",
            "title": "Fail Hard",
            "description": "Hard problem that failed.",
            "difficulty": "hard",
            "tags": ["dp"],
            "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
        },
        {
            "problem_id": "cand-easy",
            "title": "Candidate Easy",
            "description": "Easy practice problem.",
            "difficulty": "easy",
            "tags": ["dp"],
            "test_cases": [{"input": {"x": 2}, "expected_output": 2}],
        },
        {
            "problem_id": "cand-medium",
            "title": "Candidate Medium",
            "description": "Medium practice problem.",
            "difficulty": "medium",
            "tags": ["dp"],
            "test_cases": [{"input": {"x": 3}, "expected_output": 3}],
        },
        {
            "problem_id": "cand-hard-multi",
            "title": "Candidate Hard Multi",
            "description": "Hard practice problem with two tags.",
            "difficulty": "hard",
            "tags": ["dp", "graph"],
            "test_cases": [{"input": {"x": 4}, "expected_output": 4}],
        },
    ]
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_gradient_orders_easy_first_with_cost_and_dimensions(tmp_path):
    """Issue #91: gradient output order, cost fallback chain, dimensions."""
    dataset = _gradient_dataset(tmp_path)
    history = tmp_path / "results"
    history.mkdir(parents=True, exist_ok=True)
    records = [
        # fail-hard: 2 failed records with known costs 0.2 + 0.4 (mean 0.3)
        _trace_record("fail-hard", status="failed", cost="0.2"),
        _trace_record("fail-hard", status="failed", cost="0.4"),
        # Level costs come from OTHER (evaluated) problems: easy level has a
        # known-cost record; medium level only an unknown-usage one.
        _trace_record("solved-easy", status="success", cost="0.1"),
        _trace_record("solved-medium", status="success", cost=None),
    ]
    # Evaluated problems must exist in the dataset to map their difficulty.
    dataset_payload = json.loads(dataset.read_text(encoding="utf-8"))
    dataset_payload.extend(
        [
            {
                "problem_id": "solved-easy",
                "title": "Solved Easy",
                "description": "Already solved easy problem.",
                "difficulty": "easy",
                "tags": ["dp"],
                "test_cases": [{"input": {"x": 9}, "expected_output": 9}],
            },
            {
                "problem_id": "solved-medium",
                "title": "Solved Medium",
                "description": "Already solved medium problem.",
                "difficulty": "medium",
                "tags": ["dp"],
                "test_cases": [{"input": {"x": 8}, "expected_output": 8}],
            },
        ]
    )
    dataset.write_text(json.dumps(dataset_payload), encoding="utf-8")
    (history / "vanilla_results.json").write_text(
        json.dumps(records), encoding="utf-8"
    )

    report = RecommendationEngine(history, dataset_path=dataset).analyze()

    # Selection by relevance: fail-hard matches its own failed group and is
    # already evaluated... it is excluded (evaluated); candidates remain.
    items = {item["problem_id"]: item for item in report["recommended_problems"]}
    assert set(items) == {"cand-easy", "cand-medium", "cand-hard-multi"}
    # Gradient: easy -> medium -> hard.
    assert report["recommended_problem_ids"] == [
        "cand-easy",
        "cand-medium",
        "cand-hard-multi",
    ]
    # Cost estimate: per-difficulty level mean (hard level mean = 0.3).
    assert items["cand-easy"]["estimated_cost_usd"] == pytest.approx(0.1)
    assert items["cand-medium"]["estimated_cost_usd"] is None
    assert items["cand-hard-multi"]["estimated_cost_usd"] == pytest.approx(0.3)
    assert report["total_estimated_cost_usd"] == pytest.approx(0.4)
    assert report["unknown_cost_problem_count"] == 1
    # Dimensions: only tags whose weak group actually matched ("graph" has
    # no failed history, so it is not a weak dimension).
    assert items["cand-easy"]["expected_improvement_dimensions"] == ["dp"]
    assert items["cand-hard-multi"]["expected_improvement_dimensions"] == ["dp"]
    assert report["covered_dimensions"] == ["dp"]
