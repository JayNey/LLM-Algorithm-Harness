"""Tests for heuristic model capability maps and experiment panel integration."""

import pytest

from src.capability import build_capability_map
from src.experiment_panel import _build_panel_data, _render_panel


def _comparison():
    return {
        "generated_at": "2026-09-23T00:00:00",
        "experiment": {"experiment_id": "exp-1", "name": "fixture"},
        "combinations": [
            {
                "model": "model-a",
                "strategy": "vanilla",
                "denominator": {"total": 4},
                "formal": {"rate": 0.75},
                "sample_validation": {"rate": 1.0},
                "fix_rate": {"rate": 0.5},
                "actual_consumption": {
                    "avg_tokens_per_problem": 100,
                    "avg_calls_per_problem": 1,
                    "elapsed_seconds": 0.2,
                },
                "by_difficulty": {"easy": {"solved": 2, "total": 2, "rate": 1.0}},
                "by_tags": {"dp": {"solved": 2, "total": 3, "rate": 2 / 3}},
                "cost": {"known": True, "total_cost_usd": 0.1},
            },
            {
                "model": "model-a",
                "strategy": "cot",
                "denominator": {"total": 2},
                "formal": {"rate": 0.5},
                "sample_validation": {"rate": 0.5},
                "fix_rate": {"rate": None},
                "actual_consumption": {
                    "avg_tokens_per_problem": 200,
                    "avg_calls_per_problem": 2,
                    "elapsed_seconds": 0.3,
                },
                "by_difficulty": {"hard": {"solved": 1, "total": 2, "rate": 0.5}},
                "by_tags": {"graph": {"solved": 1, "total": 2, "rate": 0.5}},
                "cost": {"known": True, "total_cost_usd": 0.2},
            },
        ],
        "model_comparison": {"strategies": {}, "cost_effectiveness": [], "cost_unknown_models": []},
        "error_analysis": {"categories": {"wrong_answer": 1}},
    }


def test_capability_map_has_five_dimensions_and_heatmap():
    capability = build_capability_map(_comparison())
    assert capability["dimension_labels"] == [
        "algorithm_design",
        "code_implementation",
        "debugging",
        "optimization",
        "boundary_handling",
    ]
    assert capability["models"]["model-a"]["dimensions"]["code_implementation"] == 0.75
    assert any(
        cell["dimension"] == "dp" or cell["dimension"] == "tag:dp" for cell in capability["heatmap"]
    )
    assert capability["heuristic_note"]


def test_panel_embeds_capability_chart_and_heatmap():
    data = _build_panel_data(_comparison())
    html = _render_panel(data)
    assert "能力图谱雷达图" in html
    assert "capability-heatmap" in html
    assert "capability" in html.lower()


def _heatmap_comparison(counts):
    return {
        "combinations": [
            {
                "model": model,
                "strategy": strategy,
                "repeat": repeat,
                "by_difficulty": {"easy": values},
                "by_tags": {"array": values},
            }
            for model, strategy, repeat, values in counts
        ]
    }


def test_heatmap_pools_strategy_and_repeat_counts_instead_of_rates():
    comparison = _heatmap_comparison(
        [
            ("model-a", "vanilla", 0, {"solved": 1, "total": 1, "rate": 1.0}),
            ("model-a", "cot", 0, {"solved": 0, "total": 9, "rate": 0.0}),
            ("model-a", "vanilla", 1, {"solved": 2, "total": 2, "rate": None}),
            ("model-b", "vanilla", 0, {"solved": 1, "total": 2, "rate": 0.5}),
        ]
    )
    rows = build_capability_map(comparison)["heatmap"]
    assert rows == [
        {"model": model, "dimension": dimension, "success": solved, "total": total, "rate": rate}
        for model, solved, total, rate in [("model-a", 3, 12, 0.25), ("model-b", 1, 2, 0.5)]
        for dimension in ["easy", "tag:array"]
    ]
    from itertools import permutations

    for order in permutations(comparison["combinations"]):
        assert build_capability_map({"combinations": order})["heatmap"] == rows


def test_heatmap_zero_denominator_stays_unknown_and_empty_combo_is_neutral():
    empty = ("model-a", "vanilla", 0, {"solved": 0, "total": 0, "rate": 1.0})
    rows = build_capability_map(_heatmap_comparison([empty]))["heatmap"]
    assert all(row["success"] == 0 and row["total"] == 0 and row["rate"] is None for row in rows)
    valid = ("model-a", "cot", 0, {"solved": 2, "total": 3, "rate": 0.1})
    rows = build_capability_map(_heatmap_comparison([empty, valid]))["heatmap"]
    assert all(row["success"] == 2 and row["total"] == 3 and row["rate"] == 2 / 3 for row in rows)
    assert build_capability_map({})["heatmap"] == []


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"solved": 1, "rate": 1.0},
        {"solved": 0, "total": None},
        {"solved": None, "total": 1},
        {"solved": 0, "total": -1},
        {"solved": -1, "total": 1},
        {"solved": 2, "total": 1},
        {"solved": True, "total": 1},
        {"solved": 1, "total": "2"},
    ],
)
def test_heatmap_unknown_or_invalid_counts_never_become_confident_rates(values):
    unknown = ("model-a", "cot", 0, values)
    valid = ("model-a", "vanilla", 0, {"solved": 1, "total": 2})
    for counts in ([unknown], [valid, unknown], [unknown, valid]):
        rows = build_capability_map(_heatmap_comparison(counts))["heatmap"]
        assert all(
            row["success"] is None and row["total"] is None and row["rate"] is None for row in rows
        )


def test_panel_heatmap_reconciles_real_comparison_group_counts():
    from src.experiment_report import _combo_metrics

    meta = {
        "dataset": {
            "problems": [
                {"problem_id": pid, "difficulty": "easy", "tags": ["array", "dp"]}
                for pid in ["p1", "p2"]
            ]
        }
    }
    combos = []
    for strategy, repeat, statuses in [
        ("vanilla", 0, ["success", "success"]),
        ("cot", 0, ["wrong_answer", "success"]),
        ("vanilla", 1, ["wrong_answer", "wrong_answer"]),
    ]:
        combo = {
            "combo_id": f"{strategy}-{repeat}",
            "model": "model-a",
            "strategy": strategy,
            "repeat": repeat,
        }
        results = [
            {"problem_id": pid, "status": status} for pid, status in zip(["p1", "p2"], statuses)
        ]
        combos.append(_combo_metrics(meta, combo, {}, results, {"problems": []}))
    comparison = _comparison()
    comparison["combinations"] = combos
    data = _build_panel_data(comparison)
    for row in data["capability"]["heatmap"]:
        assert row["success"] == 3
        assert row["total"] == 6
        assert row["rate"] == 0.5
        group, key = (
            ("by_tags", row["dimension"][4:])
            if row["dimension"].startswith("tag:")
            else ("by_difficulty", row["dimension"])
        )
        assert row["success"] == sum(combo[group][key]["solved"] for combo in combos)
        assert row["total"] == sum(combo[group][key]["total"] for combo in combos)
    assert len(data["capability"]["heatmap"]) == 3
    assert '"success": 3, "total": 6, "rate": 0.5' in _render_panel(data)
