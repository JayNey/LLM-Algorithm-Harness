"""Hand-computed trade-offs, cohort checks, and offline CLI coverage for #92."""

import argparse
import copy
import json
from unittest.mock import patch

import pytest

from src.main import main
from src.pareto import build_pareto_analysis, write_pareto_artifacts


def combo(model, cost, solved=5, total=10, *, strategy="vanilla", repeat=1):
    return {
        "model": model,
        "strategy": strategy,
        "repeat": repeat,
        "solved": solved,
        "denominator": {"total": total},
        "pass_rate_over_total": 0.1234,  # Deliberately wrong: recompute from counts.
        "cost": {"known": cost is not None, "total_cost_usd": cost},
        "formal": {"evaluable": total, "solved": solved},
    }


def comparison(rows, identifier="exp-a"):
    return {
        "experiment": {
            "experiment_id": identifier,
            "code_version": {"git_commit": "fixed-commit", "git_dirty": False},
            "dataset": {"sha256": "same-dataset", "problem_ids": [f"p{i}" for i in range(10)]},
            "budget": {"max_calls": 3},
            "sandbox_config": {"backend": "docker", "timeout_seconds": 5},
            "problem_filters": None,
            "models": [
                {
                    "model": name,
                    "provider": "openai",
                    "temperature": 0.7,
                    "api_key": "must-not-export",
                }
                for name in sorted({r["model"] for r in rows})
            ],
            "strategies": [
                {"name": name, "max_iterations": 1}
                for name in sorted({r["strategy"] for r in rows})
            ],
        },
        "combinations": rows,
    }


def points_by_model(analysis):
    return {point["model"]: point for point in analysis["points"]}


def test_exact_dominance_ties_and_budget_recommendations():
    data = comparison(
        [
            combo("cheap", 1, 5),
            combo("middle", 2, 7),
            combo("pro", 4, 9),
            combo("bad", 3, 6),
            combo("same-cost-worse", 2, 6),
            combo("same-accuracy-expensive", 3, 7),
            combo("tie", 2, 7),
        ]
    )
    analysis = build_pareto_analysis([data], budgets=[0.5, 1, 2, 3, 4])
    points = points_by_model(analysis)
    assert {p["model"] for p in analysis["points"] if p["pareto_optimal"]} == {
        "cheap",
        "middle",
        "tie",
        "pro",
    }
    assert points["bad"]["dominated_by"]
    assert points["middle"]["mean_accuracy"] == 0.7
    assert points["tie"]["pareto_optimal"]
    assert analysis["best_value"]["point_id"] == points["cheap"]["id"]
    recs = analysis["budget_recommendations"]
    assert [r["feasible"] for r in recs] == [False, True, True, True, True]
    indexed = {p["id"]: p for p in analysis["points"]}
    assert [indexed[r["point_id"]]["mean_accuracy"] for r in recs[1:]] == [0.5, 0.7, 0.7, 0.9]
    assert "must-not-export" not in json.dumps(analysis)


def test_repeats_use_average_cost_and_count_based_rate():
    data = comparison([combo("a", 1, 4), combo("a", 3, 8, repeat=2), combo("b", 2, 5)])
    analysis = build_pareto_analysis([data])
    a = points_by_model(analysis)["a"]
    assert a["mean_cost_usd"] == 2
    assert a["mean_accuracy"] == 0.6
    assert a["repeats"] == 2
    assert a["cost_range_usd"] == [1, 3]
    assert a["accuracy_range"] == [0.4, 0.8]
    assert not points_by_model(analysis)["b"]["pareto_optimal"]


def test_multiple_experiments_average_same_settings_and_keep_variants_separate():
    first = comparison([combo("a", 1, 4)])
    second = comparison([combo("a", 3, 8)], "exp-b")
    analysis = build_pareto_analysis([first, second])
    assert len(analysis["points"]) == 1
    assert analysis["points"][0]["mean_cost_usd"] == 2
    assert analysis["points"][0]["sources"] == ["exp-a", "exp-b"]
    second["experiment"]["models"][0]["temperature"] = 0.2
    analysis = build_pareto_analysis([first, second])
    assert len(analysis["points"]) == 2
    assert len({p["variant"] for p in analysis["points"]}) == 2


def test_unknown_cost_in_any_repeat_excludes_whole_variant():
    data = comparison([combo("a", 1), combo("a", None, repeat=2), combo("b", 2)])
    analysis = build_pareto_analysis([data])
    assert set(points_by_model(analysis)) == {"b"}
    assert analysis["excluded"][0]["reasons"] == ["unknown_cost"]
    assert analysis["excluded"][0]["repeats"] == 2


def test_zero_cost_and_zero_success_are_explicit():
    analysis = build_pareto_analysis(
        [comparison([combo("free", 0, 4), combo("paid", 2, 8)])], budgets=[0]
    )
    free = points_by_model(analysis)["free"]
    assert free["pareto_optimal"]
    assert free["expected_solved_per_usd"] is None
    assert analysis["best_value"]["point_id"] == free["id"]
    assert analysis["budget_recommendations"][0]["point_id"] == free["id"]
    empty = build_pareto_analysis([comparison([combo("none", 0, 0)])])
    assert empty["best_value"]["feasible"] is False


def test_formal_metric_does_not_use_sample_successes():
    data = comparison([combo("sample-only", 1, 10), combo("hidden", 2, 8)])
    data["combinations"][0]["formal"] = {"evaluable": 0, "solved": 0}
    analysis = build_pareto_analysis([data], accuracy_metric="formal")
    assert set(points_by_model(analysis)) == {"hidden"}
    assert analysis["accuracy_metric"] == "formal"
    assert analysis["excluded"]


@pytest.mark.parametrize("cost", [-1, float("nan"), float("inf"), True, "1"])
def test_invalid_cost_not_used_as_a_free_point(cost):
    analysis = build_pareto_analysis([comparison([combo("bad", cost)])])
    assert not analysis["points"]
    assert analysis["excluded"]


@pytest.mark.parametrize("budget", [-1, float("nan"), float("inf"), True])
def test_invalid_budget_rejected(budget):
    with pytest.raises(ValueError):
        build_pareto_analysis([comparison([])], budgets=[budget])


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset", {"sha256": "different", "problem_ids": ["p"]}),
        ("budget", {"max_calls": 4}),
        ("sandbox_config", {"backend": "host"}),
        ("problem_filters", {"limit": 3}),
        ("code_version", {"git_commit": "different-commit", "git_dirty": False}),
    ],
)
def test_different_cohorts_rejected(field, value):
    first, second = comparison([combo("a", 1)]), comparison([combo("a", 1)], "exp-b")
    second["experiment"][field] = value
    with pytest.raises(ValueError, match="different datasets"):
        build_pareto_analysis([first, second])


def test_different_denominators_and_duplicate_repeats_rejected():
    with pytest.raises(ValueError, match="denominators"):
        build_pareto_analysis([comparison([combo("a", 1), combo("b", 2, total=20)])])
    with pytest.raises(ValueError, match="Duplicate"):
        build_pareto_analysis([comparison([combo("a", 1), combo("a", 2)])])
    with pytest.raises(ValueError, match="distinct"):
        build_pareto_analysis([comparison([combo("a", 1)]), comparison([combo("a", 1)])])


def test_legacy_single_file_works_but_unverifiable_multi_file_does_not():
    first = {"combinations": [combo("a", 1)]}
    assert build_pareto_analysis([first])["points"]
    with pytest.raises(ValueError):
        build_pareto_analysis([first, first])


def test_dirty_code_snapshot_cannot_be_averaged_across_experiments():
    first, second = comparison([combo("a", 1)]), comparison([combo("a", 2)], "exp-b")
    second["experiment"]["code_version"]["git_dirty"] = True
    with pytest.raises(ValueError, match="snapshots"):
        build_pareto_analysis([first, second])


def test_strict_dominance_keeps_a_small_real_cost_difference():
    data = comparison([combo("a", 0.50000001), combo("b", 0.50000002)])
    assert points_by_model(build_pareto_analysis([data]))["b"]["pareto_optimal"] is False


def test_tiny_known_cost_does_not_emit_infinity(tmp_path):
    analysis = build_pareto_analysis([comparison([combo("tiny", 1e-309)])])
    assert analysis["points"][0]["expected_solved_per_usd"] is None
    write_pareto_artifacts(analysis, tmp_path)
    json.dumps(analysis, allow_nan=False)


def test_artifacts_and_cli_do_not_modify_inputs(tmp_path):
    source = tmp_path / "experiment"
    source.mkdir()
    input_file = source / "comparison.json"
    input_file.write_text(json.dumps(comparison([combo("a", 1), combo("b", 2, 8)])))
    original = input_file.read_bytes()
    output = tmp_path / "analysis"
    with patch(
        "sys.argv",
        [
            "harness",
            "pareto",
            "--experiments",
            str(source),
            "--output-dir",
            str(output),
            "--budgets",
            "0",
            "1",
            "2",
        ],
    ):
        with pytest.raises(SystemExit) as stopped:
            main()
    assert stopped.value.code == 0
    assert input_file.read_bytes() == original
    report = json.loads((output / "pareto.json").read_text())
    assert report["budget_recommendations"][0]["feasible"] is False
    assert (output / "pareto.png").read_bytes().startswith(b"\x89PNG")
    assert "性价比之王" in (output / "PARETO.md").read_text()


def test_empty_artifact_chart_and_escaped_labels(tmp_path):
    analysis = build_pareto_analysis([comparison([])])
    write_pareto_artifacts(analysis, tmp_path)
    assert (tmp_path / "pareto.png").read_bytes().startswith(b"\x89PNG")
    assert analysis["best_value"]["point_id"] is None
    analysis = build_pareto_analysis([comparison([combo("a|<tag>", 1)])])
    write_pareto_artifacts(analysis, tmp_path)
    assert "a\\|&lt;tag&gt;" in (tmp_path / "PARETO.md").read_text()


def test_cli_missing_or_duplicate_input_has_no_output(tmp_path):
    output = tmp_path / "out"
    for inputs in ([tmp_path / "missing"], [tmp_path, tmp_path]):
        with patch(
            "sys.argv",
            ["harness", "pareto", "--experiments", *map(str, inputs), "--output-dir", str(output)],
        ):
            with pytest.raises(SystemExit) as stopped:
                main()
        assert stopped.value.code == 1
        assert not output.exists()


def test_analysis_does_not_mutate_comparison():
    data = comparison([combo("a", 1)])
    original = copy.deepcopy(data)
    build_pareto_analysis([data])
    assert data == original


def comparison_payload(rows, identifier="exp-a"):
    payload = comparison(rows, identifier)
    payload["experiment"]["dataset"]["problem_ids"] = ["p0", "p1"]
    return payload


def _pareto_exp_dir(tmp_path, name, combos):
    exp_dir = tmp_path / name
    exp_dir.mkdir()
    comparison = comparison_payload(rows=combos, identifier=name)
    (exp_dir / "comparison.json").write_text(json.dumps(comparison), encoding="utf-8")
    return exp_dir


def test_pareto_handler_writes_artifacts(tmp_path, capsys):
    from src.main import run_pareto_command

    # Two experiments share dataset/git snapshots so the multi-experiment
    # compatibility check passes.
    exp_a = _pareto_exp_dir(tmp_path, "exp-a", [combo("m1", 1.0, solved=8)])
    exp_b = _pareto_exp_dir(tmp_path, "exp-b", [combo("m2", 2.0, solved=9)])
    out_dir = tmp_path / "pareto-out"
    args = argparse.Namespace(
        experiments=[str(exp_a), str(exp_b)],
        budgets=None,
        accuracy_metric="overall",
        output_dir=str(out_dir),
    )
    assert run_pareto_command(args) == 0
    out = capsys.readouterr().out
    assert "frontier point" in out
    assert (out_dir / "pareto.json").exists()


def test_pareto_handler_rejects_duplicate_inputs(tmp_path, capsys):
    from src.main import run_pareto_command

    exp = _pareto_exp_dir(tmp_path, "exp-a", [combo("m1", 1.0, solved=8)])
    args = argparse.Namespace(
        experiments=[str(exp), str(exp)],
        budgets=None,
        accuracy_metric="overall",
        output_dir=str(tmp_path / "out"),
    )
    assert run_pareto_command(args) == 1
    assert "Duplicate experiment input" in capsys.readouterr().err
