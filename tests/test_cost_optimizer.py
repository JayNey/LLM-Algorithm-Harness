"""
Cost optimization advisor tests (issue #56a).

All expectations are hand-computed against a small comparison fixture:
three combinations — cheap/low-accuracy, expensive/high-accuracy, and a
priced mid-tier — plus one cost-unknown combination.
"""

import pytest

from src.cost_optimizer import (
    build_advisory,
    optimize_budget,
    rank_combinations,
    recommend,
)


def _combo(model, strategy, solved, total, cost, by_difficulty=None):
    return {
        "model": model,
        "strategy": strategy,
        "solved": solved,
        "pass_rate_over_total": solved / total if total else None,
        "cost": {"total_cost_usd": cost, "known": cost is not None},
        "by_difficulty": by_difficulty or {},
        "denominator": {"total": total, "completed": total, "budget_exhausted": 0},
    }


@pytest.fixture
def comparison():
    """Hand-computed fixture (10 problems per combo):

    - budget-vanilla:  5 solved, $1.00  → acc 0.50, ratio 5.0
    - pro-vanilla:     9 solved, $4.00  → acc 0.90, ratio 2.25
    - mid-cot:         7 solved, $2.00  → acc 0.70, ratio 3.5
    - mystery-vanilla: cost unknown     → excluded from ranking
    """
    return {
        "experiment": {"experiment_id": "exp-test"},
        "combinations": [
            _combo(
                "budget-model",
                "vanilla",
                5,
                10,
                1.00,
                {"easy": {"solved": 3, "total": 4}, "medium": {"solved": 2, "total": 4}},
            ),
            _combo(
                "pro-model",
                "vanilla",
                9,
                10,
                4.00,
                {"easy": {"solved": 4, "total": 4}, "hard": {"solved": 3, "total": 4}},
            ),
            _combo(
                "mid-model",
                "cot",
                7,
                10,
                2.00,
                {"medium": {"solved": 2, "total": 4}, "hard": {"solved": 2, "total": 4}},
            ),
            _combo("mystery-model", "vanilla", 8, 10, None),
        ],
    }


# ============================================================================
# Ranking and three-objective recommendations (task 1)
# ============================================================================


class TestRanking:
    def test_ranking_sorted_by_ratio_descending(self, comparison):
        ranking = rank_combinations(comparison)
        assert [row["ratio"] for row in ranking["ranking"]] == [5.0, 3.5, 2.25]
        assert ranking["ranking"][0]["model"] == "budget-model"

    def test_cost_unknown_excluded_and_annotated(self, comparison):
        ranking = rank_combinations(comparison)
        assert [row["model"] for row in ranking["excluded"]] == ["mystery-model"]
        assert ranking["excluded"][0]["note"] == "成本未知"
        assert ranking["excluded"][0]["cost_usd"] is None


class TestRecommend:
    def test_highest_accuracy_ignores_cost(self, comparison):
        rec = recommend(comparison, "highest_accuracy")
        assert (rec["model"], rec["strategy"]) == ("pro-model", "vanilla")
        assert rec["accuracy"] == 0.9

    def test_best_value_prefers_ratio(self, comparison):
        rec = recommend(comparison, "best_value")
        assert rec["model"] == "budget-model"
        assert rec["ratio"] == 5.0

    def test_lowest_cost_respects_min_accuracy(self, comparison):
        rec = recommend(comparison, "lowest_cost", min_accuracy=0.6)
        # Only pro-model (0.9) and mid-model (0.7) clear 0.6; mid is cheaper
        assert rec["model"] == "mid-model"
        assert rec["cost_usd"] == 2.00

    def test_lowest_cost_infeasible_when_nothing_clears_bar(self, comparison):
        rec = recommend(comparison, "lowest_cost", min_accuracy=0.95)
        assert rec["feasible"] is False
        assert "无满足约束" in rec["note"]

    def test_unknown_objective_rejected(self, comparison):
        with pytest.raises(ValueError):
            recommend(comparison, "cheapest_possible")


# ============================================================================
# Budget optimizer (task 2)
# ============================================================================


class TestBudgetOptimizer:
    def test_layers_pick_best_throughput_within_budget(self, comparison):
        plan = optimize_budget(comparison, budget=10.0, min_accuracy=0.5)
        # easy: budget-model (3/4, ratio 5.0 beats pro 4/4, ratio 2.25)
        # hard: mid-model wins on throughput (3.5) despite pro's higher accuracy
        # medium: only budget-model has medium history (2/4)
        assert plan["layers"]["easy"]["feasible"] is True
        assert plan["layers"]["easy"]["model"] == "budget-model"
        assert plan["layers"]["hard"]["feasible"] is True
        assert plan["layers"]["hard"]["model"] == "mid-model"
        assert plan["coverage"] == sum(
            e.get("problems", 0) for e in plan["layers"].values() if e.get("feasible")
        )
        assert plan["estimated_cost"] <= 10.0

    def test_min_accuracy_filters_layers(self, comparison):
        plan = optimize_budget(comparison, budget=10.0, min_accuracy=0.75)
        # medium history: budget 0.5 and mid 0.5 both fall below 0.75
        assert plan["layers"]["medium"]["feasible"] is False
        # easy still feasible via budget-model (0.75 exactly meets the bar)
        assert plan["layers"]["easy"]["feasible"] is True

    def test_layers_without_history_are_annotated(self, comparison):
        plan = optimize_budget(comparison, budget=10.0, min_accuracy=0.0)
        # No combination has hard history except pro/mid; budget layer untouched
        assert plan["layers"]["medium"]["feasible"] is True
        hard = plan["layers"]["hard"]
        assert hard["feasible"] is True
        # A layer nobody covers stays explicit
        missing = optimize_budget(
            {"combinations": [comparison["combinations"][0]]},
            budget=10.0,
            min_accuracy=0.0,
        )
        assert missing["layers"]["hard"]["feasible"] is False
        assert "无历史数据" in missing["layers"]["hard"]["note"]

    def test_full_advisory_payload(self, comparison):
        payload = build_advisory(comparison, budget=10.0, min_accuracy=0.5)
        assert payload["selected_objective"] == "best_value"
        assert payload["ranking"]["ranking"]
        assert set(payload["recommendations"].keys()) == {
            "highest_accuracy",
            "best_value",
            "lowest_cost",
        }
        assert "budget_plan" in payload
