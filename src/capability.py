"""Heuristic model capability map for fixed-budget experiment reports."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

DIMENSIONS = [
    "algorithm_design",
    "code_implementation",
    "debugging",
    "optimization",
    "boundary_handling",
]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_capability_map(comparison: dict[str, Any]) -> dict[str, Any]:
    """Build radar dimensions and difficulty/tag heatmap from comparison metrics.

    The dimensions are transparent heuristics: formal/sample pass rates stand
    in for algorithm and boundary correctness, repair rate measures debugging,
    and token efficiency measures optimization. Missing denominators remain
    null instead of being converted into a confident zero.
    """
    combos = comparison.get("combinations", [])
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for combo in combos:
        by_model[combo.get("model", "unknown")].append(combo)

    models = {}
    for model, entries in by_model.items():
        formal = [item["formal"]["rate"] for item in entries if item.get("formal", {}).get("rate") is not None]
        sample = [item["sample_validation"]["rate"] for item in entries if item.get("sample_validation", {}).get("rate") is not None]
        repair = [item["fix_rate"]["rate"] for item in entries if item.get("fix_rate", {}).get("rate") is not None]
        efficiency = []
        for item in entries:
            rate = item.get("formal", {}).get("rate")
            tokens = item.get("actual_consumption", {}).get("avg_tokens_per_problem")
            if rate is not None and isinstance(tokens, (int, float)) and tokens > 0:
                efficiency.append(rate / (1.0 + tokens / 1000.0))
        dimensions = {
            "algorithm_design": _mean(formal or sample),
            "code_implementation": _mean(sample),
            "debugging": _mean(repair),
            "optimization": _mean(efficiency),
            "boundary_handling": _mean(formal),
        }
        known = {key: value for key, value in dimensions.items() if value is not None}
        ranked = sorted(known.items(), key=lambda item: item[1], reverse=True)
        models[model] = {
            "dimensions": dimensions,
            "strengths": [key for key, _ in ranked[:3]],
            "weaknesses": [key for key, _ in ranked[-3:]],
            "sample_count": sum(item.get("denominator", {}).get("total", 0) for item in entries),
        }

    heatmap: dict[str, dict[str, dict[str, int | float | None]]] = defaultdict(dict)
    for combo in combos:
        model = combo.get("model", "unknown")
        for difficulty, values in (combo.get("by_difficulty") or {}).items():
            heatmap[model][difficulty] = {
                "success": values.get("solved", 0),
                "total": values.get("total", 0),
                "rate": values.get("rate"),
            }
        for tag, values in (combo.get("by_tags") or {}).items():
            heatmap[model][f"tag:{tag}"] = {
                "success": values.get("solved", 0),
                "total": values.get("total", 0),
                "rate": values.get("rate"),
            }

    heatmap_rows = []
    for model, cells in heatmap.items():
        for dimension, cell in cells.items():
            heatmap_rows.append({"model": model, "dimension": dimension, **cell})
    return {
        "dimension_labels": DIMENSIONS,
        "dimension_descriptions": {
            "algorithm_design": "正式/隐藏评测正确率",
            "code_implementation": "公开样例通过率",
            "debugging": "失败后修复率",
            "optimization": "正式通过率与 Token 消耗的效率分数",
            "boundary_handling": "独立隐藏测试通过率",
        },
        "models": models,
        "heatmap": heatmap_rows,
        "heuristic_note": "能力维度基于评测结果启发式估计，不代表对模型内部能力的因果测量。",
    }
