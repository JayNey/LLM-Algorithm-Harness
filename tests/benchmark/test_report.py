"""Tests for learning curve report generation."""

import os
from datetime import datetime

from pathlib import Path

import pytest

os.environ.setdefault("MPLBACKEND", "Agg")

from src.benchmark.analysis import TrendAnalyzer
from src.benchmark.history import BenchmarkHistoryStorage
from src.benchmark.report import ReportGenerator


@pytest.fixture
def storage(tmp_path):
    return BenchmarkHistoryStorage(tmp_path / "history")


@pytest.fixture
def generator(storage):
    return ReportGenerator(storage, TrendAnalyzer(storage))


def _seed_two_models(storage):
    for index, accuracy in enumerate([0.5, 0.7]):
        storage.save_result(
            "suite-a",
            "model-a",
            {"strategies": {"vanilla": {"accuracy": accuracy}}},
            timestamp=datetime(2026, 10, 1, index, 0, 0),
        )
    for index, accuracy in enumerate([0.4, 0.9]):
        storage.save_result(
            "suite-a",
            "model-b",
            {"strategies": {"vanilla": {"accuracy": accuracy}}},
            timestamp=datetime(2026, 10, 2, index, 0, 0),
        )


def test_generate_report_full_two_models(storage, generator, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # analyzer plot defaults land in ./results/benchmark
    _seed_two_models(storage)
    out = tmp_path / "report.md"

    result = generator.generate_report(
        ["model-a", "model-b"], output_path=out, include_comparison=True
    )

    assert result == out
    content = out.read_text(encoding="utf-8")
    assert "# Learning Curve Report" in content
    assert "## Model Comparison" in content
    assert "## Version Comparison" in content
    assert "| model-a | model-b |" in content
    assert "Mean Accuracy" in content
    assert "Best Performing Model:** model-b" in content  # 0.65 vs 0.6
    # plots are generated into the analyzer's default ./results/benchmark dir
    assert (tmp_path / "results" / "benchmark" / "learning_curve_model-a.png").exists()
    assert (tmp_path / "results" / "benchmark" / "model_comparison.png").exists()


def test_generate_report_without_comparison(storage, generator, tmp_path):
    _seed_two_models(storage)
    out = tmp_path / "report-no-cmp.md"

    generator.generate_report(["model-a", "model-b"], output_path=out, include_comparison=False)

    content = out.read_text(encoding="utf-8")
    # include_comparison only suppresses the comparison PLOT; the version
    # comparison table is emitted whenever more than one model is requested.
    assert "## Model Comparison" not in content
    assert "## Version Comparison" in content
    assert "## model-a" in content


def test_generate_report_tolerates_models_without_data(storage, generator, tmp_path):
    _seed_two_models(storage)
    out = tmp_path / "report-ghost.md"

    result = generator.generate_report(
        ["model-a", "ghost"], output_path=out, include_comparison=False
    )

    content = result.read_text(encoding="utf-8")
    assert "## model-a" in content
    assert "Best Performing Model:** model-a" in content
    # "ghost" section header is emitted but has no statistics block
    assert "## ghost" in content
    assert content.count("### Statistics") == 1


def test_generate_report_default_output_path(storage, generator, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_two_models(storage)

    result = generator.generate_report(["model-a"], include_comparison=False)

    assert result.parent == Path("results") / "benchmark"
    assert result.name.startswith("learning_curve_report_")
    assert (tmp_path / result).exists()
