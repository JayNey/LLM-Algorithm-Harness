"""Cost/accuracy trade-offs over comparable completed experiment records (#92)."""

from __future__ import annotations

import hashlib
import io
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import Any

from src.utils.secrets import is_sensitive_key, redact_sensitive_data


def _number(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be numeric")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    try:
        display = float(amount)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} cannot be represented in report numbers") from exc
    if not math.isfinite(display) or (amount > 0 and display == 0):
        raise ValueError(f"{name} cannot be represented in report numbers")
    return amount


def _count(value: Any, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'non-negative'} integer")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _without_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _without_secrets(v) for k, v in value.items() if not is_sensitive_key(k)}
    if isinstance(value, list):
        return [_without_secrets(v) for v in value]
    return value


def _variant(meta: Mapping[str, Any], model: str, strategy: str) -> str:
    model_configs = [c for c in meta.get("models", []) if c.get("model") == model]
    strategy_configs = [c for c in meta.get("strategies", []) if c.get("name") == strategy]
    if len(model_configs) > 1 or len(strategy_configs) > 1:
        raise ValueError("Ambiguous model/strategy settings in experiment metadata")
    settings = {
        "model": _without_secrets(model_configs[0]) if model_configs else None,
        "strategy": _without_secrets(strategy_configs[0]) if strategy_configs else None,
    }
    return hashlib.sha256(_canonical(settings).encode()).hexdigest()[:12]


def _validate_cohorts(comparisons: Sequence[Mapping[str, Any]]) -> None:
    if len(comparisons) < 2:
        return
    signatures = []
    sources = set()
    for comparison in comparisons:
        meta = comparison.get("experiment", {})
        dataset = meta.get("dataset", {})
        code_version = meta.get("code_version") or {}
        identifier = meta.get("experiment_id")
        if not identifier or identifier in sources:
            raise ValueError("Multiple experiments require distinct experiment IDs")
        sources.add(identifier)
        ids = dataset.get("problem_ids")
        if (
            not dataset.get("sha256")
            or not isinstance(ids, list)
            or not ids
            or "sandbox_config" not in meta
            or not meta.get("models")
            or not meta.get("strategies")
            or not code_version.get("git_commit")
            or code_version.get("git_dirty") is not False
        ):
            raise ValueError("Multiple experiments require dataset and evaluation/config snapshots")
        signatures.append(
            _canonical(
                {
                    "dataset_sha256": dataset["sha256"],
                    "problem_ids": sorted(ids),
                    "budget": meta.get("budget"),
                    "sandbox_config": meta["sandbox_config"],
                    "problem_filters": meta.get("problem_filters"),
                    "git_commit": code_version["git_commit"],
                }
            )
        )
    if len(set(signatures)) != 1:
        raise ValueError(
            "Experiments have different datasets, selections, budgets, sandbox settings or code versions"
        )


def _observation(combo: Mapping[str, Any], metric: str) -> dict[str, Any]:
    cost = combo.get("cost") or {}
    if cost.get("known") is not True or cost.get("total_cost_usd") is None:
        raise ValueError("unknown_cost")
    amount = _number(cost["total_cost_usd"], "cost")
    total = _count((combo.get("denominator") or {}).get("total"), "total", positive=True)
    if metric == "formal":
        formal = combo.get("formal") or {}
        denominator = _count(formal.get("evaluable"), "formal_evaluable", positive=True)
        solved = _count(formal.get("solved"), "formal_solved")
        if denominator > total:
            raise ValueError("formal denominator exceeds total")
    else:
        denominator = total
        solved = _count(combo.get("solved"), "solved")
    if solved > denominator:
        raise ValueError("solved exceeds denominator")
    if combo.get("token_budget_unsupported"):
        raise ValueError("unsupported_token_budget")
    return {
        "cost": amount,
        "accuracy": Decimal(solved) / denominator,
        "total": total,
        "denominator": denominator,
        "solved": solved,
    }


def build_pareto_analysis(
    comparisons: Sequence[Mapping[str, Any]],
    *,
    budgets: Sequence[float] = (),
    accuracy_metric: str = "overall",
) -> dict[str, Any]:
    """Average repeats equally, then minimize cost and maximize success rate.

    One unknown/invalid repeat excludes its entire combination variant. Prices
    are observed estimates; different parameter settings remain separate points.
    """
    if accuracy_metric not in {"overall", "formal"}:
        raise ValueError("accuracy_metric must be overall or formal")
    if not comparisons:
        raise ValueError("At least one comparison is required")
    for comparison in comparisons:
        if not isinstance(comparison, Mapping) or not isinstance(
            comparison.get("combinations"), list
        ):
            raise ValueError("Comparison must contain a combinations list")
    _validate_cohorts(comparisons)
    budget_values = sorted({_number(b, "budget") for b in budgets})
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    excluded = []
    for index, comparison in enumerate(comparisons):
        meta = comparison.get("experiment") or {}
        source = meta.get("experiment_id") or f"input-{index + 1}"
        seen = set()
        for row_index, combo in enumerate(comparison["combinations"]):
            if not isinstance(combo, Mapping):
                raise ValueError("Combination records must be mappings")
            model, strategy = combo.get("model"), combo.get("strategy")
            if (
                not isinstance(model, str)
                or not model
                or not isinstance(strategy, str)
                or not strategy
            ):
                excluded.append({"source": source, "reason": "missing_model_or_strategy"})
                continue
            variant = _variant(meta, model, strategy)
            # Real exports have combo_id or repeat. Legacy single files may omit
            # both, in which case list entries are independent observations.
            identity = (
                model,
                strategy,
                variant,
                combo.get("combo_id", combo.get("repeat", row_index)),
            )
            if identity in seen:
                raise ValueError("Duplicate combination/repeat in comparison")
            seen.add(identity)
            groups[(model, strategy, variant)].append({"source": source, "row": combo})

    internal: list[dict[str, Any]] = []
    denominator_pairs = set()
    for (model, strategy, variant), records in sorted(groups.items()):
        observations = []
        reasons = set()
        for record in records:
            try:
                observations.append(_observation(record["row"], accuracy_metric))
            except ValueError as exc:
                reasons.add(str(exc))
        if reasons:
            excluded.append(
                {
                    "model": model,
                    "strategy": strategy,
                    "variant": variant,
                    "repeats": len(records),
                    "reasons": sorted(reasons),
                }
            )
            continue
        totals = {(o["total"], o["denominator"]) for o in observations}
        if len(totals) != 1:
            raise ValueError("Repeated combination has inconsistent dataset/accuracy denominators")
        denominator_pairs.update(totals)
        count = len(observations)
        mean_cost = sum((o["cost"] for o in observations), Decimal(0)) / count
        mean_accuracy = sum((o["accuracy"] for o in observations), Decimal(0)) / count
        internal.append(
            {
                "id": f"point-{len(internal) + 1}",
                "model": model,
                "strategy": strategy,
                "variant": variant,
                "repeats": count,
                "sources": sorted({r["source"] for r in records}),
                "total_problems": observations[0]["total"],
                "accuracy_denominator": observations[0]["denominator"],
                "cost": mean_cost,
                "accuracy": mean_accuracy,
                "cost_range_usd": [
                    float(min(o["cost"] for o in observations)),
                    float(max(o["cost"] for o in observations)),
                ],
                "accuracy_range": [
                    float(min(o["accuracy"] for o in observations)),
                    float(max(o["accuracy"] for o in observations)),
                ],
            }
        )
    if len(denominator_pairs) > 1:
        raise ValueError("Combinations have different dataset/accuracy denominators")

    for point in internal:
        point["dominated_by"] = [
            other["id"]
            for other in internal
            if other["cost"] <= point["cost"]
            and other["accuracy"] >= point["accuracy"]
            and (other["cost"] < point["cost"] or other["accuracy"] > point["accuracy"])
        ]
        point["pareto_optimal"] = not point["dominated_by"]
    frontier = sorted(
        (p for p in internal if p["pareto_optimal"]),
        key=lambda p: (p["cost"], -p["accuracy"], p["id"]),
    )
    positive = [p for p in frontier if p["accuracy"] > 0]
    free = [p for p in positive if p["cost"] == 0]
    best = (
        max(free, key=lambda p: (p["accuracy"], p["id"]))
        if free
        else (
            max(positive, key=lambda p: (p["accuracy"] / p["cost"], p["accuracy"], -p["cost"]))
            if positive
            else None
        )
    )
    if not budget_values:
        budget_values = sorted({p["cost"] for p in frontier})
    recommendations = []
    for budget in budget_values:
        candidates = [p for p in frontier if p["cost"] <= budget]
        chosen = max(candidates, key=lambda p: (p["accuracy"], -p["cost"])) if candidates else None
        recommendations.append(
            {
                "budget_usd": float(budget),
                "feasible": chosen is not None,
                "point_id": chosen["id"] if chosen else None,
            }
        )

    points = []
    for point in internal:
        cost, accuracy = point["cost"], point["accuracy"]
        ratio = accuracy * point["accuracy_denominator"] / cost if cost else None
        ratio_value = float(ratio) if ratio is not None else None
        points.append(
            {k: v for k, v in point.items() if k not in {"cost", "accuracy"}}
            | {
                "mean_cost_usd": float(cost),
                "mean_accuracy": float(accuracy),
                "expected_solved_per_usd": (
                    ratio_value if ratio_value is not None and math.isfinite(ratio_value) else None
                ),
            }
        )
    result: dict[str, Any] = redact_sensitive_data(
        {
            "schema_version": "1.0",
            "accuracy_metric": accuracy_metric,
            "cost_basis": "mean_total_cost_usd_per_dataset_run",
            "sources": [
                c.get("experiment", {}).get("experiment_id") or f"input-{i + 1}"
                for i, c in enumerate(comparisons)
            ],
            "points": points,
            "excluded": excluded,
            "frontier_ids": [p["id"] for p in frontier],
            "best_value": {
                "feasible": best is not None,
                "point_id": best["id"] if best else None,
                "basis": "expected_solved_per_usd; known zero-cost successes preferred",
            },
            "budget_recommendations": recommendations,
            "note": "Historical means and ranges are descriptive, not guaranteed future accuracy or billing.",
        }
    )
    return result


def _cell(value: Any) -> str:
    return escape(str(value), quote=False).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_pareto_markdown(analysis: Mapping[str, Any]) -> str:
    points = {p["id"]: p for p in analysis["points"]}
    lines = [
        "# 成本-准确率帕累托分析",
        "",
        f"- 成功率口径：`{analysis['accuracy_metric']}`；成本为同一题集一次运行的平均总美元成本。",
        "- 重复运行等权平均；展示的是历史观测。预算建议以平均成本判断，不保证下一次运行不超支。",
        "",
        "| 模型 / 策略 / 配置 | 次数 | 平均成本（范围） | 平均成功率（范围） | 前沿 |",
        "|---|---:|---:|---:|---|",
    ]
    for point in points.values():
        lines.append(
            f"| {_cell(point['model'])} / {_cell(point['strategy'])} / {point['variant']} "
            f"| {point['repeats']} | ${point['mean_cost_usd']:.6g} "
            f"(${point['cost_range_usd'][0]:.6g}–${point['cost_range_usd'][1]:.6g}) "
            f"| {point['mean_accuracy']:.1%} "
            f"({point['accuracy_range'][0]:.1%}–{point['accuracy_range'][1]:.1%}) "
            f"| {'是' if point['pareto_optimal'] else '否'} |"
        )
    lines.extend(["", "## 推荐", ""])
    best = points.get(analysis["best_value"]["point_id"])
    if best:
        lines.append(
            f"- 性价比之王：{_cell(best['model'])} × {_cell(best['strategy'])} "
            f"（配置 {best['variant']}，成功率 {best['mean_accuracy']:.1%}，平均 ${best['mean_cost_usd']:.6g}）。"
        )
    else:
        lines.append("- 没有成本已知且成功率大于零的可推荐组合。")
    for recommendation in analysis["budget_recommendations"]:
        chosen = points.get(recommendation["point_id"])
        label = (
            (
                f"{_cell(chosen['model'])} × {_cell(chosen['strategy'])} / {chosen['variant']} "
                f"（{chosen['mean_accuracy']:.1%}）"
            )
            if chosen
            else "无平均成本在预算内的方案"
        )
        lines.append(f"- 预算 ${recommendation['budget_usd']:.6g}：{label}")
    lines.extend(["", "## 排除记录", ""])
    for item in analysis["excluded"]:
        lines.append(
            f"- {_cell(item.get('model', '未命名'))} / {_cell(item.get('strategy', '未命名'))}："
            f"{_cell(', '.join(item.get('reasons', [item.get('reason', 'invalid')])))}"
        )
    if not analysis["excluded"]:
        lines.append("无。")
    lines.extend(["", "![帕累托前沿](pareto.png)", ""])
    return "\n".join(lines)


def render_pareto_chart(analysis: Mapping[str, Any]) -> bytes:
    """Standalone scatter plot, with numeric labels linked to a model legend."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    points = analysis["points"]
    fig = Figure(figsize=(10, max(5, 0.3 * len(points) + 3)), dpi=120)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    if not points:
        ax.text(
            0.5,
            0.5,
            "No comparable cost / accuracy records",
            transform=ax.transAxes,
            ha="center",
            va="center",
        )
    frontier = sorted(
        (p for p in points if p["pareto_optimal"]),
        key=lambda p: (p["mean_cost_usd"], p["mean_accuracy"]),
    )
    ax.plot(
        [p["mean_cost_usd"] for p in frontier],
        [p["mean_accuracy"] for p in frontier],
        color="#15803d",
        alpha=0.5,
        linewidth=1,
        label="Pareto frontier",
    )
    for index, point in enumerate(points, 1):
        optimal = point["pareto_optimal"]
        ax.scatter(
            point["mean_cost_usd"],
            point["mean_accuracy"],
            color="#15803d" if optimal else "#94a3b8",
            marker="D" if optimal else "o",
            s=55,
            label=f"{index}. {point['model']} / {point['strategy']} / {point['variant'][:6]}",
        )
        ax.annotate(
            str(index),
            (point["mean_cost_usd"], point["mean_accuracy"]),
            xytext=(5, 6 + (index % 3) * 9),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_xlabel("Mean total cost per dataset run (USD)")
    ax.set_ylabel(f"Success rate ({analysis['accuracy_metric']})")
    ax.set_title("Cost / accuracy Pareto frontier")
    ax.set_ylim(-0.05, 1.08)
    ax.grid(alpha=0.2)
    if points:
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)
    fig.tight_layout()
    stream = io.BytesIO()
    fig.savefig(stream, format="png", bbox_inches="tight")
    return stream.getvalue()


def write_pareto_artifacts(analysis: Mapping[str, Any], output_dir: str | Path) -> None:
    directory = Path(output_dir)
    chart = render_pareto_chart(analysis)
    markdown = render_pareto_markdown(analysis)
    payload = json.dumps(analysis, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pareto.json").write_text(payload, encoding="utf-8")
    (directory / "PARETO.md").write_text(markdown, encoding="utf-8")
    (directory / "pareto.png").write_bytes(chart)
