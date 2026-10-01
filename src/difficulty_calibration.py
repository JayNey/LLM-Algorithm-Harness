"""
Difficulty recalibration from historical evaluation data (issue #82).

Problem difficulty labels come from the source site and often disagree with
actual LLM performance. The calibrator aggregates per-problem success rates
from historical ``*_results.json`` files, classifies each problem by
configurable thresholds, and produces a recalibrated dataset plus a change
report for human review.

Classification: success rate above the easy threshold (default 0.7) -> easy;
below the hard threshold (default 0.3) -> hard; rates equal to a threshold
fall in medium. Problems without any history keep their original label and
are listed for review.
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from src.models import Problem
from src.utils.logging import get_logger

logger = get_logger(__name__)

SKIPPED_HISTORY_FILES = {
    "metadata.json",
    "experiment.json",
    "summary.json",
    "comparison.json",
    "report.json",
}

DEFAULT_EASY_THRESHOLD = 0.7
DEFAULT_HARD_THRESHOLD = 0.3


def _iter_history_records(history_path: Path) -> Iterable[dict[str, Any]]:
    """Yield per-problem evaluation records from *_results.json files."""
    paths = [history_path] if history_path.is_file() else sorted(history_path.rglob("*.json"))
    for path in paths:
        if path.name in SKIPPED_HISTORY_FILES or not path.name.endswith("_results.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("history_file_unreadable", path=str(path))
            continue
        if not isinstance(payload, list):
            continue
        for record in payload:
            if isinstance(record, dict) and isinstance(record.get("problem_id"), str):
                yield record


def _record_solved(record: dict[str, Any]) -> bool:
    """Same solved semantics as the recommender: sample pass + hidden pass."""
    if record.get("status") != "success":
        return False
    hidden = record.get("hidden_result")
    return not (hidden and not hidden.get("all_passed", False))


class DifficultyCalibrator:
    """Aggregate historical performance and recalibrate difficulty labels."""

    def __init__(
        self,
        history_path: Path,
        easy_threshold: float = DEFAULT_EASY_THRESHOLD,
        hard_threshold: float = DEFAULT_HARD_THRESHOLD,
    ):
        self.history_path = history_path
        self.easy_threshold = easy_threshold
        self.hard_threshold = hard_threshold
        self.stats: dict[str, dict[str, float]] = {}

    def collect_stats(self) -> dict[str, dict[str, float]]:
        """Aggregate per-problem success rate and average iterations."""
        acc: dict[str, dict[str, float]] = {}
        for record in _iter_history_records(self.history_path):
            entry = acc.setdefault(
                record["problem_id"], {"total": 0, "solved": 0, "iterations": 0.0}
            )
            entry["total"] += 1
            iterations = record.get("iterations")
            if isinstance(iterations, list):
                entry["iterations"] += float(len(iterations))
            if _record_solved(record):
                entry["solved"] += 1
        for entry in acc.values():
            total = entry["total"]
            entry["success_rate"] = entry["solved"] / total if total else 0.0
            entry["avg_iterations"] = entry["iterations"] / total if total else 0.0
        self.stats = acc
        return acc

    def classify(self, success_rate: float) -> str:
        """Classify one success rate by the configured thresholds.

        Strictly above the easy threshold is easy, strictly below the hard
        threshold is hard; rates equal to a threshold fall in medium,
        matching the issue's ">70% / <30%" wording.
        """
        if success_rate > self.easy_threshold:
            return "easy"
        if success_rate < self.hard_threshold:
            return "hard"
        return "medium"

    def recalibrate(self, problems: list[Problem]) -> dict[str, dict[str, Any]]:
        """Return per-problem recalibration decisions.

        Each entry maps problem_id to {"original", "calibrated",
        "success_rate", "avg_iterations"}; problems without history carry
        calibrated == original (flagged by "has_data": False).
        """
        if not self.stats:
            self.collect_stats()
        decisions: dict[str, dict[str, Any]] = {}
        for problem in problems:
            stats = self.stats.get(problem.problem_id)
            if stats is None:
                decisions[problem.problem_id] = {
                    "original": problem.difficulty,
                    "calibrated": problem.difficulty,
                    "has_data": False,
                }
                continue
            calibrated = self.classify(stats["success_rate"])
            decisions[problem.problem_id] = {
                "original": problem.difficulty,
                "calibrated": calibrated,
                "success_rate": stats["success_rate"],
                "avg_iterations": stats["avg_iterations"],
                "has_data": True,
            }
        return decisions


def build_change_report(decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarise recalibration: distribution before/after and changes."""
    before: dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    after: dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    changes: list[dict[str, Any]] = []
    no_data_ids: list[str] = []
    for problem_id, decision in decisions.items():
        before[decision["original"]] = before.get(decision["original"], 0) + 1
        after[decision["calibrated"]] = after.get(decision["calibrated"], 0) + 1
        if not decision.get("has_data"):
            no_data_ids.append(problem_id)
        if decision["calibrated"] != decision["original"]:
            changes.append(
                {
                    "problem_id": problem_id,
                    "original": decision["original"],
                    "calibrated": decision["calibrated"],
                    "success_rate": round(decision.get("success_rate", 0.0), 4),
                    "avg_iterations": round(decision.get("avg_iterations", 0.0), 2),
                }
            )
    return {
        "distribution_before": before,
        "distribution_after": after,
        "changes": changes,
        "no_data_count": len(no_data_ids),
        "no_data_problem_ids": no_data_ids,
        "total": len(decisions),
    }


def format_change_report(report: dict[str, Any]) -> str:
    """Render the change report as Markdown."""
    lines = [
        "# 难度重标注报告",
        "",
        f"- 题目总数：{report['total']}",
        f"- 难度变更数：{len(report['changes'])}",
        f"- 无历史数据题数：{report['no_data_count']}",
        "",
        "## 难度分布对比",
        "",
        "| 难度 | 重标注前 | 重标注后 |",
        "|------|----------|----------|",
    ]
    for difficulty in ("easy", "medium", "hard"):
        lines.append(
            f"| {difficulty} | {report['distribution_before'][difficulty]} "
            f"| {report['distribution_after'][difficulty]} |"
        )
    if report["no_data_problem_ids"]:
        lines.append("")
        lines.append("无历史数据题目：" + "、".join(report["no_data_problem_ids"]))
    lines.extend(["", "## 难度变更明细", ""])
    if report["changes"]:
        lines.append("| 题目 | 原难度 | 新难度 | 成功率 | 平均迭代 |")
        lines.append("|------|--------|--------|--------|----------|")
        for change in report["changes"]:
            lines.append(
                f"| {change['problem_id']} | {change['original']} | {change['calibrated']} "
                f"| {change['success_rate']:.2%} | {change['avg_iterations']:.2f} |"
            )
    else:
        lines.append("无难度变更。")
    return "\n".join(lines) + "\n"


def write_calibrated_dataset(
    problems: list[Problem],
    decisions: dict[str, dict[str, Any]],
    output_path: str,
) -> None:
    """Write the full problem list with recalibrated difficulty labels."""
    payload = []
    for problem in problems:
        item = problem.model_dump(mode="json")
        item["difficulty"] = decisions[problem.problem_id]["calibrated"]
        payload.append(item)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
