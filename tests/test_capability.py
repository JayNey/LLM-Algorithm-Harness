"""Tests for heuristic model capability maps and experiment panel integration."""

from src.capability import build_capability_map
from src.experiment_panel import _build_panel_data, _render_panel


def _comparison():
    return {
        "generated_at": "2026-09-23T00:00:00",
        "experiment": {"experiment_id": "exp-1", "name": "fixture"},
        "combinations": [
            {
                "model": "model-a", "strategy": "vanilla",
                "denominator": {"total": 4},
                "formal": {"rate": 0.75},
                "sample_validation": {"rate": 1.0},
                "fix_rate": {"rate": 0.5},
                "actual_consumption": {"avg_tokens_per_problem": 100, "avg_calls_per_problem": 1, "elapsed_seconds": 0.2},
                "by_difficulty": {"easy": {"solved": 2, "total": 2, "rate": 1.0}},
                "by_tags": {"dp": {"solved": 2, "total": 3, "rate": 2 / 3}},
                "cost": {"known": True, "total_cost_usd": 0.1},
            },
            {
                "model": "model-a", "strategy": "cot",
                "denominator": {"total": 2},
                "formal": {"rate": 0.5},
                "sample_validation": {"rate": 0.5},
                "fix_rate": {"rate": None},
                "actual_consumption": {"avg_tokens_per_problem": 200, "avg_calls_per_problem": 2, "elapsed_seconds": 0.3},
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
        "algorithm_design", "code_implementation", "debugging", "optimization", "boundary_handling"
    ]
    assert capability["models"]["model-a"]["dimensions"]["code_implementation"] == 0.75
    assert any(cell["dimension"] == "dp" or cell["dimension"] == "tag:dp" for cell in capability["heatmap"])
    assert capability["heuristic_note"]


def test_panel_embeds_capability_chart_and_heatmap():
    data = _build_panel_data(_comparison())
    html = _render_panel(data)
    assert "能力图谱雷达图" in html
    assert "capability-heatmap" in html
    assert "capability" in html.lower()
