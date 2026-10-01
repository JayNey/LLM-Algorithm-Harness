"""Tests for benchmark trend analysis (learning curve tracking)."""

import os
from datetime import datetime

import pytest

os.environ.setdefault("MPLBACKEND", "Agg")

from src.benchmark.analysis import TrendAnalyzer
from src.benchmark.history import BenchmarkHistoryStorage


@pytest.fixture
def storage(tmp_path):
    return BenchmarkHistoryStorage(tmp_path / "history")


@pytest.fixture
def analyzer(storage):
    return TrendAnalyzer(storage)


def seed(storage, model_id, accuracies, suite="suite-a", day=1):
    for index, accuracy in enumerate(accuracies):
        storage.save_result(
            suite,
            model_id,
            {"strategies": {"vanilla": {"accuracy": accuracy}}},
            timestamp=datetime(2026, 10, day, index, 0, 0),
        )


def test_extract_time_series_groups_and_sorts(storage, analyzer):
    seed(storage, "m-a", [0.5, 0.7])
    seed(storage, "m-b", [0.4], suite="suite-b")

    series = analyzer.extract_time_series()

    assert set(series) == {"m-a", "m-b"}
    assert [acc for _, acc in series["m-a"]] == [0.5, 0.7]
    assert series["m-a"][0][0] < series["m-a"][1][0]


def test_extract_time_series_filters_model_and_suite(storage, analyzer):
    seed(storage, "m-a", [0.5], suite="suite-a")
    seed(storage, "m-b", [0.4], suite="suite-b")

    only_a = analyzer.extract_time_series(model_id="m-a")
    assert set(only_a) == {"m-a"}

    only_b_suite = analyzer.extract_time_series(suite_name="suite-b")
    assert set(only_b_suite) == {"m-b"}


def test_extract_time_series_skips_results_without_accuracy(storage, analyzer):
    storage.save_result("suite-a", "m-a", {"strategies": {}}, timestamp=datetime(2026, 10, 1))
    seed(storage, "m-a", [0.6])

    series = analyzer.extract_time_series()
    assert [acc for _, acc in series["m-a"]] == [0.6]


def test_plot_learning_curve_writes_file(storage, analyzer, tmp_path):
    seed(storage, "m-a", [0.5, 0.6, 0.8])
    out = tmp_path / "curve.png"

    result = analyzer.plot_learning_curve("m-a", output_path=out)

    assert result == out
    assert out.exists() and out.stat().st_size > 0


def test_plot_learning_curve_raises_without_data(storage, analyzer, tmp_path):
    with pytest.raises(ValueError, match="No data found"):
        analyzer.plot_learning_curve("ghost", output_path=tmp_path / "x.png")


def test_plot_model_comparison_writes_file(storage, analyzer, tmp_path):
    seed(storage, "m-a", [0.5, 0.7])
    seed(storage, "m-b", [0.4, 0.9])
    out = tmp_path / "comparison.png"

    result = analyzer.plot_model_comparison(output_path=out)

    assert result == out
    assert out.exists()


def test_plot_model_comparison_filters_and_raises_on_empty(storage, analyzer, tmp_path):
    seed(storage, "m-a", [0.5])
    with pytest.raises(ValueError, match="No data found"):
        analyzer.plot_model_comparison(model_ids=["ghost"], output_path=tmp_path / "x.png")
    result = analyzer.plot_model_comparison(model_ids=["m-a"], output_path=tmp_path / "y.png")
    assert result.exists()


def test_calculate_statistics(storage, analyzer):
    seed(storage, "m-a", [0.4, 0.6, 0.8])

    stats = analyzer.calculate_statistics("m-a")

    assert stats["data_points"] == 3
    assert stats["mean_accuracy"] == pytest.approx(0.6)
    assert stats["min_accuracy"] == 0.4
    assert stats["max_accuracy"] == 0.8
    assert stats["growth_rate"] == pytest.approx(0.4)
    assert stats["relative_growth"] == pytest.approx(1.0)


def test_calculate_statistics_without_growth_for_single_point(storage, analyzer):
    seed(storage, "m-a", [0.7])
    stats = analyzer.calculate_statistics("m-a")
    assert "growth_rate" not in stats


def test_calculate_statistics_raises_without_data(storage, analyzer):
    with pytest.raises(ValueError, match="No data found"):
        analyzer.calculate_statistics("ghost")


def test_compare_versions_pairwise_differences(storage, analyzer):
    seed(storage, "m-a", [0.4, 0.6], day=1)  # mean 0.5
    seed(storage, "m-b", [0.7, 0.9], day=2)  # mean 0.8

    comparison = analyzer.compare_versions(["m-a", "m-b", "ghost"])

    assert "ghost" not in comparison["models"]
    assert comparison["models"]["m-a"]["mean_accuracy"] == pytest.approx(0.5)
    diffs = comparison["pairwise_differences"]
    assert len(diffs) == 1
    assert diffs[0]["model_a"] == "m-a"
    assert diffs[0]["model_b"] == "m-b"
    assert diffs[0]["accuracy_difference"] == pytest.approx(0.3)


def test_compare_versions_without_pairwise_for_single_model(storage, analyzer):
    seed(storage, "m-a", [0.5])
    comparison = analyzer.compare_versions(["m-a"])
    assert "pairwise_differences" not in comparison
