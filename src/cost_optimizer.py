"""
Cost optimization advisor (issue #56a).

Reads a completed experiment's ``comparison.json`` and produces a
cost-effectiveness ranking, three-objective combination recommendations,
and a per-difficulty budget plan. Analysis only: no evaluation is re-run,
and recommendations are heuristic — based on historical data without any
guarantee about future behavior or global optimality.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)

DIFFICULTY_LAYERS = ["easy", "medium", "hard"]

OBJECTIVES = ("highest_accuracy", "best_value", "lowest_cost")


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _accuracy(combo: Dict[str, Any]) -> Optional[float]:
    return combo.get("pass_rate_over_total")


def _combo_rows(comparison: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One ranked row per combination with cost-known filtering."""
    rows = []
    for combo in comparison.get("combinations", []):
        cost_info = combo.get("cost") or {}
        known = bool(cost_info.get("known")) and (cost_info.get("total_cost_usd") or 0) > 0
        accuracy = _accuracy(combo)
        cost = cost_info.get("total_cost_usd")
        ratio = (combo.get("solved", 0) / cost) if known and cost else None
        rows.append(
            {
                "model": combo.get("model"),
                "strategy": combo.get("strategy"),
                "accuracy": accuracy,
                "cost_usd": cost if known else None,
                "ratio": round(ratio, 3) if ratio is not None else None,
                "available": known,
                "note": None if known else "成本未知",
            }
        )
    return rows


def rank_combinations(comparison: Dict[str, Any]) -> Dict[str, Any]:
    """Cost-effectiveness ranking; cost-unknown rows are excluded but listed."""
    rows = _combo_rows(comparison)
    ranked = sorted(
        (row for row in rows if row["available"]),
        key=lambda row: row["ratio"],
        reverse=True,
    )
    excluded = [row for row in rows if not row["available"]]
    return {"ranking": ranked, "excluded": excluded}


def recommend(
    comparison: Dict[str, Any],
    objective: str,
    min_accuracy: float = 0.0,
) -> Dict[str, Any]:
    """Pick one combination under the requested objective."""
    if objective not in OBJECTIVES:
        raise ValueError(f"Unknown objective: {objective}")
    rows = [row for row in _combo_rows(comparison) if row["available"]]

    def _eligible(row: Dict[str, Any]) -> bool:
        return row["accuracy"] is not None and row["accuracy"] >= min_accuracy

    if objective == "highest_accuracy":
        candidates = sorted(
            rows, key=lambda r: (r["accuracy"] or 0.0, r["ratio"] or 0.0), reverse=True
        )
        basis = "准确率最高（不考虑成本）"
    elif objective == "best_value":
        candidates = sorted(rows, key=lambda r: r["ratio"] or 0.0, reverse=True)
        basis = "性价比（通过题数/成本）最高"
    else:  # lowest_cost
        candidates = sorted(
            (row for row in rows if _eligible(row)),
            key=lambda r: (r["cost_usd"], -(r["accuracy"] or 0.0)),
        )
        basis = f"满足最低准确率 {min_accuracy:.0%} 的组合中成本最低"

    if not candidates or candidates[0]["model"] is None:
        return {
            "objective": objective,
            "feasible": False,
            "note": "无满足约束的方案" if objective == "lowest_cost" else "无可用的成本已知组合",
        }
    chosen = candidates[0]
    return {
        "objective": objective,
        "feasible": True,
        "basis": basis,
        "model": chosen["model"],
        "strategy": chosen["strategy"],
        "accuracy": chosen["accuracy"],
        "cost_usd": chosen["cost_usd"],
        "ratio": chosen["ratio"],
    }


def _layer_cost(row: Dict[str, Any], layer_total: int) -> float:
    """Estimated layer cost from the row's whole-run unit economics."""
    total = 0
    for combo in row.get("_source_combos", []):
        total += combo.get("denominator", {}).get("total", 0)
    if not total:
        return 0.0
    return (row["cost_usd"] or 0.0) * layer_total / total


def optimize_budget(
    comparison: Dict[str, Any],
    budget: float,
    min_accuracy: float = 0.0,
) -> Dict[str, Any]:
    """Greedy per-difficulty plan: cheapest passing combination per layer."""
    rows = [
        row for row in _combo_rows(comparison) if row["available"] and row["accuracy"] is not None
    ]
    remaining = budget
    layers: Dict[str, Any] = {}

    for layer in DIFFICULTY_LAYERS:
        candidates = []
        for row in rows:
            by_difficulty = {}
            for combo in comparison.get("combinations", []):
                if combo.get("model") == row["model"] and combo.get("strategy") == row["strategy"]:
                    by_difficulty = combo.get("by_difficulty") or {}
                    break
            stats = by_difficulty.get(layer)
            if not stats or not stats.get("total"):
                continue
            layer_accuracy = stats.get("solved", 0) / stats["total"]
            if layer_accuracy < min_accuracy:
                continue
            candidates.append(
                {
                    "row": row,
                    "layer_accuracy": round(layer_accuracy, 4),
                    "throughput": (row["ratio"] or 0.0),
                    "layer_cost": round(
                        _layer_cost(
                            {
                                **row,
                                "_source_combos": [
                                    c
                                    for c in comparison.get("combinations", [])
                                    if c.get("model") == row["model"]
                                    and c.get("strategy") == row["strategy"]
                                ],
                            },
                            stats["total"],
                        ),
                        6,
                    ),
                    "layer_total": stats["total"],
                }
            )
        if not candidates:
            layers[layer] = {"feasible": False, "note": "无历史数据或无满足约束的组合"}
            continue
        candidates.sort(key=lambda c: (c["throughput"], c["layer_accuracy"]), reverse=True)
        chosen = candidates[0]
        if chosen["layer_cost"] > remaining:
            layers[layer] = {
                "feasible": False,
                "note": f"预算不足（该层估算成本 ${chosen['layer_cost']:.4f}，剩余 ${remaining:.4f}）",
            }
            continue
        remaining -= chosen["layer_cost"]
        layers[layer] = {
            "feasible": True,
            "model": chosen["row"]["model"],
            "strategy": chosen["row"]["strategy"],
            "layer_accuracy": chosen["layer_accuracy"],
            "estimated_cost": chosen["layer_cost"],
            "problems": chosen["layer_total"],
        }

    feasible_layers = [entry for entry in layers.values() if entry.get("feasible")]
    total_problems = sum(entry.get("problems", 0) for entry in feasible_layers)
    if total_problems:
        estimated_accuracy = round(
            sum(
                entry.get("layer_accuracy", 0) * entry.get("problems", 0)
                for entry in feasible_layers
            )
            / total_problems,
            4,
        )
    else:
        estimated_accuracy = None

    return {
        "budget": budget,
        "min_accuracy": min_accuracy,
        "layers": layers,
        "estimated_cost": round(budget - remaining, 6),
        "estimated_accuracy": estimated_accuracy,
        "coverage": total_problems,
    }


def build_advisory(
    comparison: Dict[str, Any],
    budget: Optional[float] = None,
    min_accuracy: float = 0.0,
    objective: str = "best_value",
) -> Dict[str, Any]:
    """Full advisory payload: ranking, recommendations, optional budget plan."""
    payload: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "experiment_id": comparison.get("experiment", {}).get("experiment_id", ""),
        "ranking": rank_combinations(comparison),
        "recommendations": {name: recommend(comparison, name, min_accuracy) for name in OBJECTIVES},
        "selected_objective": objective,
    }
    if budget is not None:
        payload["budget_plan"] = optimize_budget(comparison, budget, min_accuracy)
    return payload


def render_markdown(payload: Dict[str, Any]) -> str:
    """Render the advisory as OPTIMIZATION.md."""
    lines = [f"# 成本优化建议 — {payload.get('experiment_id', '')}", ""]
    lines.append("## 性价比排名")
    lines.append("")
    lines.append("| 模型 | 策略 | 准确率 | 成本 | 性价比 |")
    lines.append("|---|---|---:|---:|---:|")
    for row in payload["ranking"]["ranking"]:
        lines.append(
            f"| {row['model']} | {row['strategy']} | {row['accuracy']:.1%} "
            f"| ${row['cost_usd']:.4f} | {row['ratio']} |"
        )
    for row in payload["ranking"]["excluded"]:
        lines.append(
            f"| {row['model']} | {row['strategy']} | {row['accuracy'] or 0:.1%} | 未知 | — |"
        )
    lines.append("")
    lines.append("## 推荐组合")
    lines.append("")
    for name in OBJECTIVES:
        rec = payload["recommendations"][name]
        if rec.get("feasible"):
            lines.append(
                f"- **{name}**：{rec['model']} × {rec['strategy']}"
                f"（准确率 {rec['accuracy']:.1%}，成本 ${rec['cost_usd']:.4f}）—— {rec['basis']}"
            )
        else:
            lines.append(f"- **{name}**：{rec.get('note')}")
    plan = payload.get("budget_plan")
    if plan:
        lines.append("")
        lines.append(
            f"## 预算方案（预算 ${plan['budget']}，最低准确率 {plan['min_accuracy']:.0%}）"
        )
        lines.append("")
        for layer, entry in plan["layers"].items():
            if entry.get("feasible"):
                lines.append(
                    f"- **{layer}**：{entry['model']} × {entry['strategy']}"
                    f"（层准确率 {entry['layer_accuracy']:.1%}，估算 ${entry['estimated_cost']:.4f}，"
                    f"{entry['problems']} 题）"
                )
            else:
                lines.append(f"- **{layer}**：{entry['note']}")
        if plan["estimated_accuracy"] is not None:
            lines.append(
                f"- 估算总成本 ${plan['estimated_cost']:.4f}，"
                f"预期准确率 {plan['estimated_accuracy']:.1%}"
            )
        else:
            lines.append("- 无可覆盖题目，无法估算准确率")
        lines.append(f"- 覆盖题数：{plan['coverage']}")
    lines.append("")
    lines.append("> 推荐基于历史数据与启发式规则，不保证未来表现一致或全局最优。")
    lines.append("")
    return "\n".join(lines)
