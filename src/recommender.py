"""Rule-based problem weakness analysis and recommendation (issue #49).

Issue #91 additions: the recommendation list is ordered easy -> medium ->
hard (relevance stays the selection rule), each recommendation carries an
estimated practice cost derived from historical known-pricing traces, and
reports surface the weak-tag dimensions each recommendation would improve.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models import Problem
from src.problem_loader import ProblemLoader
from src.utils.secrets import redact_sensitive_data

DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}


def _record_known_cost(record: dict[str, Any]) -> tuple[float, bool]:
    """Known-pricing cost of one history record, and whether it was countable.

    Same honest criteria as the cost modules: traces with unknown usage or
    unknown pricing (or a missing/invalid total_cost) make the record
    uncountable instead of contributing a partial or fabricated amount.
    """
    traces = record.get("llm_traces")
    if not traces:
        # No traces: the record's cost cannot be verified, so it must not
        # silently pass as a free call.
        return 0.0, False
    total = 0.0
    countable = True
    for trace in traces:
        if not isinstance(trace, dict):
            countable = False
            continue
        pricing = trace.get("pricing_metadata")
        if not isinstance(pricing, dict):
            countable = False
            continue
        cost = pricing.get("total_cost")
        if (
            cost is None
            or pricing.get("usage_known") is False
            or pricing.get("pricing_known") is False
        ):
            countable = False
            continue
        try:
            amount = float(cost)
        except (TypeError, ValueError, OverflowError):
            countable = False
        else:
            if math.isfinite(amount) and amount >= 0:
                total += amount
            else:
                countable = False
    return total, countable


class RecommendationEngine:
    """Analyze historical result files and recommend unevaluated problems."""

    def __init__(
        self,
        history_path: str | Path,
        *,
        dataset_path: str | Path | None = None,
        failure_threshold: float = 0.5,
        min_samples: int = 1,
    ):
        if not 0.0 < failure_threshold <= 1.0:
            raise ValueError("failure_threshold must be between 0 and 1")
        if min_samples < 1:
            raise ValueError("min_samples must be at least 1")
        self.history_path = Path(history_path)
        if not self.history_path.exists():
            raise FileNotFoundError(f"History path not found: {history_path}")
        self.dataset_path = Path(dataset_path) if dataset_path else self._infer_dataset_path()
        self.failure_threshold = failure_threshold
        self.min_samples = min_samples

    def analyze(self, *, limit: int = 20) -> dict[str, Any]:
        """Return a weakness report and ranked, unevaluated recommendations."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        problems = self._load_dataset()
        history = list(self._iter_history_records())
        if not history:
            raise ValueError("No result records found under history path")

        evaluated_ids = {record["problem_id"] for record in history}
        problem_map = {problem.problem_id: problem for problem in problems}
        cost_by_difficulty: dict[str, tuple[float, int]] = {}
        stats: dict[str, dict[str, Any]] = defaultdict(self._new_group)
        per_problem: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "failed": 0})

        for record in history:
            problem_id = record["problem_id"]
            problem = problem_map.get(problem_id)
            if problem is None:
                continue
            failed = self._record_failed(record)
            per_problem[problem_id]["total"] += 1
            per_problem[problem_id]["failed"] += int(failed)
            cost, countable = _record_known_cost(record)
            if countable:
                difficulty = problem.difficulty or "unknown"
                summed, count = cost_by_difficulty.get(difficulty, (0.0, 0))
                cost_by_difficulty[difficulty] = (summed + cost, count + 1)
            for key, group_type in self._group_keys(problem):
                bucket = stats[key]
                bucket["type"] = group_type
                bucket["key"] = key
                bucket["total"] += 1
                bucket["failed"] += int(failed)
                bucket["problem_ids"].add(problem_id)

        weaknesses = []
        for bucket in stats.values():
            if bucket["total"] < self.min_samples:
                continue
            failure_rate = bucket["failed"] / bucket["total"]
            if failure_rate < self.failure_threshold:
                continue
            weaknesses.append(
                {
                    "type": bucket["type"],
                    "key": bucket["key"],
                    "failure_rate": failure_rate,
                    "failed": bucket["failed"],
                    "total": bucket["total"],
                    "problem_count": len(bucket["problem_ids"]),
                    "reason": (
                        f"历史评测中 {bucket['key']} 的失败率为 "
                        f"{failure_rate:.1%}（{bucket['failed']}/{bucket['total']}）"
                    ),
                }
            )
        weaknesses.sort(key=lambda item: (-item["failure_rate"], -item["failed"], item["key"]))

        recommendations = self._recommend(
            problems,
            evaluated_ids,
            weaknesses,
            limit,
            cost_by_difficulty=cost_by_difficulty,
        )
        known_costs = [
            item["estimated_cost_usd"]
            for item in recommendations
            if item["estimated_cost_usd"] is not None
        ]
        total_estimated_cost = round(sum(known_costs), 6) if known_costs else 0.0
        unknown_cost_count = sum(
            1 for item in recommendations if item["estimated_cost_usd"] is None
        )
        covered_dimensions = sorted(
            {
                dimension
                for item in recommendations
                for dimension in item["expected_improvement_dimensions"]
            }
        )
        return redact_sensitive_data(
            {
                "schema_version": "1.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "history_path": str(self.history_path),
                "dataset_path": str(self.dataset_path),
                "failure_threshold": self.failure_threshold,
                "min_samples": self.min_samples,
                "evaluated_problem_count": len(evaluated_ids),
                "history_record_count": len(history),
                "weakness_report": weaknesses,
                "recommended_problems": recommendations,
                "recommended_problem_ids": [item["problem_id"] for item in recommendations],
                "total_estimated_cost_usd": total_estimated_cost,
                "unknown_cost_problem_count": unknown_cost_count,
                "covered_dimensions": covered_dimensions,
                "recommendation_config": {
                    "dataset_path": "recommended.problems.json",
                    "problem_ids": [item["problem_id"] for item in recommendations],
                    "selection_rule": "unevaluated problems matching highest failure-rate groups",
                },
            }
        )

    def write(self, output_path: str | Path, *, limit: int = 20) -> dict[str, Any]:
        """Write report JSON and a directly usable recommended dataset beside it."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        report = self.analyze(limit=limit)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        dataset_output = output.with_name(f"{output.stem}.problems.json")
        recommended = report["recommended_problems"]
        dataset_output.write_text(
            json.dumps(recommended, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["recommendation_config"]["dataset_path"] = str(dataset_output)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report

    def _load_dataset(self) -> list[Problem]:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset path not found: {self.dataset_path}")
        return ProblemLoader().load(str(self.dataset_path))

    def _infer_dataset_path(self) -> Path:
        candidates = []
        files = (
            [self.history_path]
            if self.history_path.is_file()
            else list(self.history_path.rglob("*.json"))
        )
        for path in files:
            if path.name not in {"metadata.json", "experiment.json"}:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            value = payload.get("dataset_path")
            if not value and isinstance(payload.get("dataset"), dict):
                value = payload["dataset"].get("path")
            if value:
                candidates.extend([Path(value), path.parent / value])
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise ValueError(
            "Dataset path is required when history metadata does not contain an existing dataset_path"
        )

    def _iter_history_records(self) -> Iterable[dict[str, Any]]:
        paths = (
            [self.history_path]
            if self.history_path.is_file()
            else sorted(self.history_path.rglob("*.json"))
        )
        for path in paths:
            if path.name in {
                "metadata.json",
                "experiment.json",
                "summary.json",
                "comparison.json",
                "report.json",
            }:
                continue
            if not path.name.endswith("_results.json"):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, list):
                continue
            for record in payload:
                if isinstance(record, dict) and isinstance(record.get("problem_id"), str):
                    yield record

    @staticmethod
    def _new_group() -> dict[str, Any]:
        return {"type": "", "key": "", "total": 0, "failed": 0, "problem_ids": set()}

    @staticmethod
    def _record_failed(record: dict[str, Any]) -> bool:
        if record.get("status") != "success":
            return True
        hidden = record.get("hidden_result")
        return bool(hidden and not hidden.get("all_passed", False))

    @staticmethod
    def _group_keys(problem: Problem) -> list[tuple[str, str]]:
        tags = tuple(sorted(problem.tags))
        keys = [(f"difficulty:{problem.difficulty}", "difficulty")]
        if tags:
            keys.append((f"tags:{','.join(tags)}", "tag_combination"))
            keys.extend((f"tag:{tag}", "tag") for tag in tags)
        else:
            keys.append(("tags:unknown", "tag_combination"))
        keys.append(
            (
                f"difficulty_tags:{problem.difficulty}|{','.join(tags) or 'unknown'}",
                "difficulty_tag_combination",
            )
        )
        return keys

    @staticmethod
    def _recommend(
        problems: list[Problem],
        evaluated_ids: set[str],
        weaknesses: list[dict[str, Any]],
        limit: int,
        *,
        cost_by_difficulty: dict[str, tuple[float, int]],
    ) -> list[dict[str, Any]]:
        weakness_map = {item["key"]: item for item in weaknesses}
        scored = []
        for problem in problems:
            if problem.problem_id in evaluated_ids:
                continue
            matching = [
                weakness_map[key]
                for key, _ in RecommendationEngine._group_keys(problem)
                if key in weakness_map
            ]
            if not matching:
                continue
            matching.sort(key=lambda item: (-item["failure_rate"], -item["failed"], item["key"]))
            top = matching[0]
            scored.append(
                (
                    top["failure_rate"],
                    top["failed"],
                    len(matching),
                    problem,
                    [item["key"] for item in matching],
                )
            )
        scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3].problem_id))
        selected = scored[:limit]
        # Difficulty gradient for practice order: relevance decides WHO gets
        # in, easy-first decides the OUTPUT order (stable within a rank).
        selected.sort(key=lambda item: DIFFICULTY_RANK.get(item[3].difficulty, 3))
        output = []
        for failure_rate, failed, _, problem, matches in selected:
            data = problem.model_dump(mode="json")
            data["recommendation_reason"] = (
                f"匹配高失败率分组 {', '.join(matches)}；最高失败率 "
                f"{failure_rate:.1%}（{failed} 次失败）"
            )
            data["recommendation_score"] = failure_rate
            data["expected_improvement_dimensions"] = sorted(
                {key.split(":", 1)[1] for key in matches if key.startswith("tag:")}
            )
            estimated = RecommendationEngine._estimate_cost(problem, cost_by_difficulty)
            data["estimated_cost_usd"] = round(estimated, 6) if estimated is not None else None
            output.append(data)
        return output

    @staticmethod
    def _estimate_cost(
        problem: Problem,
        cost_by_difficulty: dict[str, tuple[float, int]],
    ) -> float | None:
        """Practice cost estimate from the difficulty's known-cost mean.

        Recommended problems are unevaluated by construction, so they have
        no own history; the difficulty level mean is the only grounded tier.
        """
        difficulty = problem.difficulty or "unknown"
        level = cost_by_difficulty.get(difficulty)
        if level and level[1]:
            return level[0] / level[1]
        return None
