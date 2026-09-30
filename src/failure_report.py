"""Aggregate recorded failure modes into descriptive reports and a PNG chart.

This module only reads completed result records. Its tag rates use all
evaluated records for the tag as the denominator, while mode shares use only
failed records. Multiple tags on one problem are counted in each tag group.
"""

from __future__ import annotations

import io
from collections import Counter
from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

FAILURE_MODES = (
    "syntax_error",
    "logic_error",
    "timeout",
    "boundary_condition",
    "understanding_error",
    "runtime_error",
    "infrastructure_error",
    "unknown",
)

MODE_LABELS = {
    "syntax_error": "语法错误",
    "logic_error": "逻辑错误",
    "timeout": "超时",
    "boundary_condition": "边界条件遗漏",
    "understanding_error": "题意理解错误",
    "runtime_error": "运行时错误",
    "infrastructure_error": "基础设施错误",
    "unknown": "无法判定",
}

_NOT_EVALUATED = {"budget_exhausted", "unsupported", "cancelled", "canceled"}
_EVALUATED_STATUSES = {"success", "failed", "error"}


def _record(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    raise TypeError("results and problem_info entries must be mappings or Pydantic models")


def _tags(result: Mapping[str, Any], info: Mapping[str, Any]) -> list[str]:
    values = info.get("tags") or result.get("tags") or []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    return sorted({value.strip() for value in values if isinstance(value, str) and value.strip()})


def _mode(result: Mapping[str, Any], info: Mapping[str, Any]) -> str:
    recorded = result.get("failure_mode")
    if recorded in FAILURE_MODES:
        return recorded

    # Old result files do not have failure_mode. Reclassify them without
    # mutating the original record or persisting inferred evidence.
    from src.failure_classifier import classify_failure_mode

    classification = classify_failure_mode(result, info)
    inferred = classification.mode if classification is not None else "unknown"
    return inferred if inferred in FAILURE_MODES else "unknown"


def summarize_failure_modes(
    results: Sequence[Mapping[str, Any] | Any],
    problem_info: Mapping[str, Mapping[str, Any] | Any] | None = None,
    *,
    min_weakness_samples: int = 3,
    top_n: int = 5,
) -> dict[str, Any]:
    """Summarize failures and tag groups with explicit denominators.

    ``budget_exhausted``, ``unsupported`` and both cancellation spellings have no completed
    evaluation, so they are absent from both denominators. Weakness rankings
    are descriptive and omit tags with fewer than ``min_weakness_samples``
    evaluated records; they do not claim statistical significance.
    """
    if min_weakness_samples < 1:
        raise ValueError("min_weakness_samples must be at least 1")
    if top_n < 0:
        raise ValueError("top_n must be non-negative")

    problem_info = problem_info or {}
    category_counts: Counter[str] = Counter()
    groups: dict[str, dict[str, Any]] = {}
    evaluated = 0
    failures = 0

    for raw_result in results:
        result = _record(raw_result)
        status = result.get("status")
        if (
            result.get("evaluation_completed") is False
            or not isinstance(status, str)
            or status in _NOT_EVALUATED
            or status not in _EVALUATED_STATUSES
        ):
            continue
        evaluated += 1
        problem_id = result.get("problem_id")
        raw_info = (problem_info.get(problem_id) or {}) if isinstance(problem_id, str) else {}
        info = _record(raw_info)
        tags = _tags(result, info)
        for tag in tags:
            groups.setdefault(tag, {"evaluated": 0, "failures": 0, "categories": Counter()})[
                "evaluated"
            ] += 1

        if status == "success":
            continue

        failures += 1
        mode = _mode(result, info)
        category_counts[mode] += 1
        for tag in tags:
            group = groups[tag]
            group["failures"] += 1
            group["categories"][mode] += 1

    by_tags: dict[str, dict[str, Any]] = {}
    for tag, group in sorted(groups.items()):
        count = group["evaluated"]
        by_tags[tag] = {
            "evaluated": count,
            "failures": group["failures"],
            "failure_rate": round(group["failures"] / count, 4),
            "categories": {
                mode: group["categories"][mode]
                for mode in FAILURE_MODES
                if group["categories"][mode]
            },
        }

    ranked = [
        {
            "tag": tag,
            "evaluated": group["evaluated"],
            "failures": group["failures"],
            "failure_rate": group["failure_rate"],
            "dominant_mode": max(
                group["categories"],
                key=lambda mode: (group["categories"][mode], -FAILURE_MODES.index(mode)),
            ),
            "dominant_count": max(group["categories"].values()),
        }
        for tag, group in by_tags.items()
        if group["evaluated"] >= min_weakness_samples and group["failures"] > 0
    ]
    ranked.sort(key=lambda item: (-item["failure_rate"], -item["failures"], item["tag"]))

    return {
        "total_evaluated": evaluated,
        "total_failures": failures,
        "categories": {
            mode: {
                "count": category_counts[mode],
                "share": round(category_counts[mode] / failures, 4) if failures else 0.0,
            }
            for mode in FAILURE_MODES
        },
        "by_tags": by_tags,
        "min_weakness_samples": min_weakness_samples,
        "top_weaknesses": ranked[:top_n],
    }


def _safe_cell(value: Any) -> str:
    return escape(str(value), quote=False).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_failure_mode_markdown(summary: Mapping[str, Any]) -> str:
    """Render one summary as a Markdown section with counts and denominators."""
    evaluated = summary.get("total_evaluated", 0)
    failures = summary.get("total_failures", 0)
    lines = [
        "## 失败模式分析",
        "",
        f"- 已评估记录：{evaluated}",
        f"- 失败记录：{failures}",
        "- 口径：类别占比以失败记录为分母；标签失败率以该标签已评估记录为分母。一个题目可计入多个标签。",
        "- 未执行、预算耗尽和不支持的记录不计入分母。",
        "",
    ]
    if not failures:
        lines.extend(["当前没有可分类的失败记录。", ""])
        return "\n".join(lines)

    lines.extend(["| 失败模式 | 次数 | 失败中占比 |", "|---|---:|---:|"])
    for mode, values in summary.get("categories", {}).items():
        if values.get("count", 0):
            label = MODE_LABELS.get(mode, mode)
            lines.append(f"| {_safe_cell(label)} (`{mode}`) | {values['count']} | {values['share']:.1%} |")
    lines.extend(["", "### 按题目标签", ""])
    by_tags = summary.get("by_tags", {})
    if by_tags:
        lines.extend(["| 标签 | 失败 / 已评估 | 失败率 | 最常见失败模式 |", "|---|---:|---:|---|"])
        for tag, values in sorted(
            by_tags.items(), key=lambda item: (-item[1]["failure_rate"], item[0])
        ):
            modes = values.get("categories", {})
            dominant = max(modes, key=modes.get) if modes else None
            label = MODE_LABELS.get(dominant, dominant) if dominant else "—"
            lines.append(
                f"| {_safe_cell(tag)} | {values['failures']} / {values['evaluated']} "
                f"| {values['failure_rate']:.1%} | {_safe_cell(label)} |"
            )
    else:
        lines.append("没有题目标签数据。")

    minimum = summary.get("min_weakness_samples", 3)
    lines.extend(
        [
            "",
            "### 高频弱项（描述性排序）",
            "",
            f"仅列出至少 {minimum} 条已评估记录且出现失败的标签；小样本不足以推断模型的稳定弱点。",
            "",
        ]
    )
    weaknesses = summary.get("top_weaknesses", [])
    if weaknesses:
        lines.extend(["| 标签 | 失败 / 已评估 | 失败率 | 主要失败模式 |", "|---|---:|---:|---|"])
        for item in weaknesses:
            label = MODE_LABELS.get(item["dominant_mode"], item["dominant_mode"])
            lines.append(
                f"| {_safe_cell(item['tag'])} | {item['failures']} / {item['evaluated']} "
                f"| {item['failure_rate']:.1%} | {_safe_cell(label)}（{item['dominant_count']}） |"
            )
    else:
        lines.append("当前没有达到最小样本数的弱项标签。")
    return "\n".join(lines) + "\n"


def render_failure_mode_chart(summary: Mapping[str, Any]) -> bytes | None:
    """Render a horizontal mode distribution chart as PNG bytes."""
    if not summary.get("total_failures", 0):
        return None

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    categories = [
        (mode, values)
        for mode, values in summary.get("categories", {}).items()
        if values.get("count", 0)
    ]
    if not categories:
        return None
    categories.sort(key=lambda pair: (pair[1]["count"], pair[0]))

    fig = Figure(figsize=(9, max(3, 0.56 * len(categories) + 1.4)), dpi=120)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    labels = [mode.replace("_", " ") for mode, _ in categories]
    counts = [values["count"] for _, values in categories]
    bars = ax.barh(labels, counts, color="#3B82F6")
    for bar, (_, values) in zip(bars, categories, strict=True):
        ax.text(
            bar.get_width() + 0.05,
            bar.get_y() + bar.get_height() / 2,
            f"{values['count']} ({values['share']:.1%})",
            va="center",
        )
    ax.set_xlim(0, max(counts) * 1.32 + 0.25)
    ax.set_xlabel("Failed records")
    ax.set_title("Failure mode distribution")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    output = io.BytesIO()
    fig.savefig(output, format="png")
    return output.getvalue()
