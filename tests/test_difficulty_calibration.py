"""
Tests for difficulty recalibration from historical evaluation data (issue #82).
"""

import argparse
import json
from pathlib import Path

import pytest

from src.difficulty_calibration import (
    DEFAULT_EASY_THRESHOLD,
    DifficultyCalibrator,
    build_change_report,
    format_change_report,
)
from src.main import run_recalibrate_command
from src.models import Problem


def write_results(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def record(problem_id, status="success", hidden_passed=True, iterations=1):
    return {
        "problem_id": problem_id,
        "status": status,
        "iterations": [{}] * iterations,
        "hidden_result": {"all_passed": hidden_passed} if hidden_passed else {"all_passed": False},
    }


def make_problem(problem_id, difficulty):
    return Problem(
        problem_id=problem_id,
        title=f"P-{problem_id}",
        description="A problem description long enough",
        difficulty=difficulty,
        tags=["tag"],
        test_cases=[{"input": {"x": 1}, "expected_output": 1}],
    )


class TestCollectStats:
    def test_aggregates_across_records_and_runs(self, tmp_path):
        write_results(
            tmp_path / "run1" / "vanilla_results.json",
            [
                record("p1", iterations=1),
                record("p1", status="failed", hidden_passed=False, iterations=3),
                record("p2", iterations=2),
            ],
        )
        write_results(
            tmp_path / "run2" / "cot_results.json",
            [record("p1", iterations=2)],
        )
        (tmp_path / "run1" / "summary.json").write_text("{}", encoding="utf-8")

        calibrator = DifficultyCalibrator(tmp_path)
        stats = calibrator.collect_stats()

        assert stats["p1"]["total"] == 3
        assert stats["p1"]["solved"] == 2
        assert stats["p1"]["success_rate"] == pytest.approx(2 / 3)
        assert stats["p1"]["avg_iterations"] == pytest.approx(2.0)
        assert stats["p2"]["success_rate"] == 1.0

    def test_failed_hidden_test_does_not_count_as_solved(self, tmp_path):
        write_results(
            tmp_path / "vanilla_results.json",
            [record("p1", status="success", hidden_passed=False)],
        )
        stats = DifficultyCalibrator(tmp_path).collect_stats()
        assert stats["p1"]["success_rate"] == 0.0

    def test_unreadable_files_are_skipped(self, tmp_path):
        write_results(tmp_path / "a_results.json", [record("p1")])
        (tmp_path / "broken_results.json").write_text("{not json", encoding="utf-8")
        stats = DifficultyCalibrator(tmp_path).collect_stats()
        assert set(stats) == {"p1"}


class TestClassify:
    def test_threshold_boundaries(self):
        calibrator = DifficultyCalibrator(Path("."), easy_threshold=0.8, hard_threshold=0.2)
        assert calibrator.classify(0.81) == "easy"
        assert calibrator.classify(0.8) == "medium"
        assert calibrator.classify(0.19) == "hard"
        assert calibrator.classify(0.2) == "medium"
        assert calibrator.classify(0.5) == "medium"

    def test_default_thresholds(self):
        calibrator = DifficultyCalibrator(Path("."))
        assert DEFAULT_EASY_THRESHOLD == 0.7
        assert calibrator.classify(0.71) == "easy"
        assert calibrator.classify(0.29) == "hard"
        assert calibrator.classify(0.5) == "medium"


class TestRecalibrate:
    def test_recalibrates_and_keeps_no_data_problems(self, tmp_path):
        write_results(
            tmp_path / "vanilla_results.json",
            [
                record("weak", status="failed", hidden_passed=False),
                record("strong", iterations=2),
            ],
        )
        calibrator = DifficultyCalibrator(tmp_path)
        calibrator.collect_stats()
        problems = [
            make_problem("weak", "easy"),
            make_problem("strong", "hard"),
            make_problem("unknown", "medium"),
        ]
        decisions = calibrator.recalibrate(problems)

        assert decisions["weak"]["calibrated"] == "hard"
        assert decisions["weak"]["original"] == "easy"
        assert decisions["weak"]["success_rate"] == 0.0
        assert decisions["strong"]["calibrated"] == "easy"
        assert decisions["strong"]["avg_iterations"] == 2.0
        assert decisions["unknown"]["calibrated"] == "medium"
        assert decisions["unknown"]["has_data"] is False


class TestChangeReport:
    def test_report_counts_changes_and_distribution(self, tmp_path):
        write_results(tmp_path / "vanilla_results.json", [record("weak", status="failed")])
        calibrator = DifficultyCalibrator(tmp_path)
        calibrator.collect_stats()
        decisions = calibrator.recalibrate(
            [make_problem("weak", "easy"), make_problem("mystery", "medium")]
        )

        report = build_change_report(decisions)
        assert report["distribution_before"] == {"easy": 1, "medium": 1, "hard": 0}
        assert report["distribution_after"]["hard"] == 1
        assert report["changes"] == [
            {
                "problem_id": "weak",
                "original": "easy",
                "calibrated": "hard",
                "success_rate": 0.0,
                "avg_iterations": 1.0,
            }
        ]
        assert report["no_data_count"] == 1
        assert report["no_data_problem_ids"] == ["mystery"]
        rendered = format_change_report(report)
        assert "难度重标注报告" in rendered
        assert "weak" in rendered
        assert "无历史数据题目：mystery" in rendered


class TestRecalibrateCommand:
    def _write_inputs(self, tmp_path):
        dataset = [
            make_problem("weak", "easy").model_dump(mode="json"),
            make_problem("strong", "hard").model_dump(mode="json"),
        ]
        (tmp_path / "problems.json").write_text(json.dumps(dataset), encoding="utf-8")
        write_results(
            tmp_path / "results" / "vanilla_results.json",
            [
                record("weak", status="failed", hidden_passed=False),
                record("strong", iterations=2),
            ],
        )

    def test_end_to_end_writes_dataset_and_report(self, tmp_path, capsys):
        self._write_inputs(tmp_path)
        args = argparse.Namespace(
            history=str(tmp_path / "results"),
            dataset=str(tmp_path / "problems.json"),
            output=str(tmp_path / "calibrated.json"),
            easy_threshold=0.7,
            hard_threshold=0.3,
            report=str(tmp_path / "report.md"),
            log_format="console",
        )
        exit_code = run_recalibrate_command(args)

        assert exit_code == 0
        calibrated = json.loads((tmp_path / "calibrated.json").read_text(encoding="utf-8"))
        by_id = {item["problem_id"]: item for item in calibrated}
        assert by_id["weak"]["difficulty"] == "hard"
        assert by_id["strong"]["difficulty"] == "easy"
        assert by_id["strong"]["title"] == "P-strong"  # other fields preserved
        report_text = (tmp_path / "report.md").read_text(encoding="utf-8")
        assert "weak" in report_text
        output = capsys.readouterr().out
        assert "changed: 2" in output

    def test_no_history_records_exits_nonzero(self, tmp_path, capsys):
        self._write_inputs(tmp_path)
        (tmp_path / "results" / "vanilla_results.json").unlink()
        args = argparse.Namespace(
            history=str(tmp_path / "results"),
            dataset=str(tmp_path / "problems.json"),
            output=str(tmp_path / "calibrated.json"),
            easy_threshold=0.7,
            hard_threshold=0.3,
            report=None,
            log_format="console",
        )
        assert run_recalibrate_command(args) == 1
        assert not (tmp_path / "calibrated.json").exists()

    def test_output_equal_to_dataset_is_rejected(self, tmp_path, capsys):
        self._write_inputs(tmp_path)
        args = argparse.Namespace(
            history=str(tmp_path / "results"),
            dataset=str(tmp_path / "problems.json"),
            output=str(tmp_path / "problems.json"),
            easy_threshold=0.7,
            hard_threshold=0.3,
            report=None,
            log_format="console",
        )
        assert run_recalibrate_command(args) == 1
        assert "must differ" in capsys.readouterr().err

    def test_empty_dataset_reports_clean_error(self, tmp_path, capsys):
        (tmp_path / "problems.json").write_text("[]", encoding="utf-8")
        write_results(tmp_path / "results" / "vanilla_results.json", [record("p1")])
        args = argparse.Namespace(
            history=str(tmp_path / "results"),
            dataset=str(tmp_path / "problems.json"),
            output=str(tmp_path / "calibrated.json"),
            easy_threshold=0.7,
            hard_threshold=0.3,
            report=None,
            log_format="console",
        )
        assert run_recalibrate_command(args) == 1
        assert "Dataset is empty" in capsys.readouterr().err

    def test_invalid_thresholds_exits_nonzero(self, tmp_path):
        args = argparse.Namespace(
            history=str(tmp_path),
            dataset=str(tmp_path / "problems.json"),
            output=str(tmp_path / "calibrated.json"),
            easy_threshold=0.3,
            hard_threshold=0.7,
            report=None,
            log_format="console",
        )
        assert run_recalibrate_command(args) == 1
        assert not (tmp_path / "calibrated.json").exists()
