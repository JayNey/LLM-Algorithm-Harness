"""
Comparison report generation for fixed-budget experiments (issue #15).

Aggregates the per-combination artifacts written by ExperimentRunner into
machine-readable (JSON/CSV) and readable (Markdown) comparison reports. All
rates carry explicit denominators: total = completed + budget-exhausted, and
failure categories reconcile against the total. Unknown pricing is reported
as unknown, never as $0.
"""

import csv
import json
from datetime import datetime
from math import comb
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.error_analysis import analyze_results
from src.utils.logging import get_logger

logger = get_logger(__name__)

FAILURE_CATEGORIES = [
    "wrong_answer",
    "code_extraction_failed",
    "model_error",
    "system_error",
    "unsupported",
    "budget_exhausted",
]


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator > 0 else None


def _combo_metrics(
    meta: Dict[str, Any],
    combo: Dict[str, Any],
    summary: Dict[str, Any],
    results: List[Dict[str, Any]],
    ledger: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute one combination's metrics with explicit denominators."""
    strategy = combo["strategy"]
    report = summary.get(strategy, {})
    problem_info = {
        problem["problem_id"]: problem for problem in meta.get("dataset", {}).get("problems", [])
    }
    total = len(results)
    solved = sum(1 for r in results if r.get("status") == "success")
    budget_exhausted = sum(1 for r in results if r.get("status") == "budget_exhausted")
    completed = total - budget_exhausted

    formal_evaluable = sum(1 for r in results if r.get("formal_evaluable"))
    formal_solved = sum(
        1
        for r in results
        if r.get("formal_evaluable")
        and r.get("hidden_result")
        and r["hidden_result"].get("all_passed")
    )
    sample_validated = sum(
        1
        for r in results
        if r.get("status") != "budget_exhausted"
        and (
            (r.get("final_result") or {}).get("all_passed", False)
            or (r.get("final_result") is None and r.get("status") == "success")
        )
    )

    failure_categories = {category: 0 for category in FAILURE_CATEGORIES}
    for r in results:
        if r.get("status") == "budget_exhausted":
            failure_categories["budget_exhausted"] += 1
        else:
            category = r.get("failure_category")
            if category:
                failure_categories[category] = failure_categories.get(category, 0) + 1

    # Fix rate: completed problems whose first visible round failed but the
    # final result passed. Single-round strategies have no fix opportunities.
    opportunities = 0
    fixed = 0
    for r in results:
        if r.get("status") == "budget_exhausted" or not r.get("iterations"):
            continue
        first = r["iterations"][0]
        first_passed = bool((first.get("sandbox_result") or {}).get("all_passed"))
        if not first_passed:
            opportunities += 1
            if r.get("status") == "success":
                fixed += 1

    problems_ledger = ledger.get("problems", [])
    calls = sum(entry.get("calls", 0) for entry in problems_ledger)
    prompt_tokens = sum(entry.get("prompt_tokens", 0) for entry in problems_ledger)
    completion_tokens = sum(entry.get("completion_tokens", 0) for entry in problems_ledger)
    reasoning_tokens = sum(entry.get("reasoning_tokens", 0) for entry in problems_ledger)
    total_tokens = sum(entry.get("total_tokens", 0) for entry in problems_ledger)
    elapsed = sum(entry.get("elapsed_seconds", 0.0) for entry in problems_ledger)

    pricing = report.get("pricing_metadata") or {}
    cost_known = not pricing.get("unknown_usage", False) and not pricing.get(
        "unknown_pricing", False
    )

    return {
        "combo_id": combo["combo_id"],
        "model": combo["model"],
        "strategy": strategy,
        "repeat": combo["repeat"],
        "token_budget_unsupported": combo.get("token_budget_unsupported", False),
        "denominator": {
            "total": total,
            "completed": completed,
            "budget_exhausted": budget_exhausted,
        },
        "solved": solved,
        "pass_rate_over_total": _rate(solved, total),
        "pass_rate_over_completed": _rate(solved, completed),
        "formal": {
            "evaluable": formal_evaluable,
            "solved": formal_solved,
            "rate": _rate(formal_solved, formal_evaluable),
        },
        "sample_validation": {
            "validated": sample_validated,
            "completed": completed,
            "rate": _rate(sample_validated, completed),
        },
        "failure_categories": failure_categories,
        "fix_rate": {
            "opportunities": opportunities,
            "fixed": fixed,
            "rate": _rate(fixed, opportunities),
        },
        "actual_consumption": {
            "calls": calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
            "elapsed_seconds": round(elapsed, 6),
            "avg_calls_per_problem": _rate(calls, total),
            "avg_tokens_per_problem": _rate(total_tokens, total),
        },
        "cost": {
            "total_cost_usd": pricing.get("total_cost") if cost_known else None,
            "known": cost_known,
        },
        "by_difficulty": _group_rates(results, problem_info, "difficulty"),
        "by_tags": _group_rates(results, problem_info, "tags"),
    }


def _group_rates(
    results: List[Dict[str, Any]],
    problem_info: Dict[str, Dict[str, Any]],
    attr: str,
) -> Dict[str, Dict[str, Any]]:
    """Group pass rates by a problem attribute; tags allow multiple groups."""
    groups: Dict[str, Dict[str, int]] = {}
    for r in results:
        info = problem_info.get(r.get("problem_id"), {})
        values = info.get(attr) or []
        if isinstance(values, str):
            values = [values]
        for value in values or ["unknown"]:
            bucket = groups.setdefault(value, {"solved": 0, "total": 0})
            bucket["total"] += 1
            if r.get("status") == "success":
                bucket["solved"] += 1
    return {
        name: {
            "solved": bucket["solved"],
            "total": bucket["total"],
            "rate": _rate(bucket["solved"], bucket["total"]),
        }
        for name, bucket in sorted(groups.items())
    }


def _aggregate_by_model_strategy(
    combos: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Collapse repeats per (model, strategy) into min/max ranges."""
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    order: List[tuple] = []
    for combo in combos:
        key = (combo["model"], combo["strategy"])
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(combo)

    range_keys = [
        "pass_rate_over_total",
        "pass_rate_over_completed",
        "formal.rate",
        "sample_validation.rate",
        "fix_rate.rate",
        "actual_consumption.avg_tokens_per_problem",
        "actual_consumption.avg_calls_per_problem",
    ]

    def _flat(combo: Dict[str, Any], dotted: str) -> Any:
        value: Any = combo
        for part in dotted.split("."):
            value = value.get(part) if isinstance(value, dict) else None
            if value is None:
                return None
        return value

    aggregated = []
    for key in order:
        members = grouped[key]
        model, strategy = key
        ranges: Dict[str, Any] = {}
        for dotted in range_keys:
            values = [v for v in (_flat(c, dotted) for c in members) if v is not None]
            if len(members) > 1 and values:
                ranges[dotted] = {"min": min(values), "max": max(values)}
            elif values:
                ranges[dotted] = {"min": values[0], "max": values[0]}
        aggregated.append(
            {
                "model": model,
                "strategy": strategy,
                "repeats": len(members),
                "ranges": ranges,
                "uncertainty_note": (
                    f"重复 {len(members)} 次：范围为跨重复的最小/最大值，"
                    "远端生成随机性不宣称为位级复现"
                    if len(members) > 1
                    else "单次运行，无跨重复范围"
                ),
            }
        )
    return aggregated


def _flat_csv_row(combo: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "combo_id": combo["combo_id"],
        "model": combo["model"],
        "strategy": combo["strategy"],
        "repeat": combo["repeat"],
        "total": combo["denominator"]["total"],
        "completed": combo["denominator"]["completed"],
        "budget_exhausted": combo["denominator"]["budget_exhausted"],
        "solved": combo["solved"],
        "pass_rate_over_total": combo["pass_rate_over_total"],
        "pass_rate_over_completed": combo["pass_rate_over_completed"],
        "formal_evaluable": combo["formal"]["evaluable"],
        "formal_solved": combo["formal"]["solved"],
        "formal_rate": combo["formal"]["rate"],
        "sample_validated": combo["sample_validation"]["validated"],
        "sample_validation_rate": combo["sample_validation"]["rate"],
        "fix_opportunities": combo["fix_rate"]["opportunities"],
        "fix_rate": combo["fix_rate"]["rate"],
        "avg_calls_per_problem": combo["actual_consumption"]["avg_calls_per_problem"],
        "avg_tokens_per_problem": combo["actual_consumption"]["avg_tokens_per_problem"],
        "elapsed_seconds": combo["actual_consumption"]["elapsed_seconds"],
        "cost_known": combo["cost"]["known"],
        "total_cost_usd": combo["cost"]["total_cost_usd"],
        "token_budget_unsupported": combo["token_budget_unsupported"],
    }
    for category in FAILURE_CATEGORIES:
        row[f"failure_{category}"] = combo["failure_categories"][category]
    return row


def _render_markdown(comparison: Dict[str, Any]) -> str:
    lines: List[str] = []
    meta = comparison.get("experiment", {})
    lines.append(f"# 固定预算实验对比报告：{meta.get('name') or meta.get('experiment_id', '')}")
    lines.append("")
    lines.append(f"- 实验目录：{meta.get('experiment_id', '')}")
    lines.append(f"- 代码版本：{meta.get('code_version', {}).get('git_commit') or '未知'}")
    dataset = meta.get("dataset", {})
    lines.append(
        f"- 题集：{dataset.get('path')}（SHA-256 `{dataset.get('sha256')}`，{dataset.get('problem_count')} 题）"
    )
    budget = meta.get("budget")
    if budget:
        lines.append(
            f"- 每题预算：调用 ≤ {budget.get('max_calls') or '∞'}，"
            f"token ≤ {budget.get('max_tokens') or '∞'}，"
            f"耗时 ≤ {budget.get('max_seconds') or '∞'} 秒"
        )
    else:
        lines.append("- 每题预算：未设置")
    lines.append("- 口径：总数 = 完成 + 预算未完成；隐藏通过率只计有独立隐藏测试的题目")
    lines.append("")
    lines.append("## 组合对比")
    lines.append("")
    lines.append(
        "| 模型 | 策略 | 重复 | 总数 | 完成 | 预算未完成 | 隐藏通过率 | 样例验证率 | 修复率 | 平均调用 | 平均 tokens | 成本 |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")

    def _fmt(value: Any, percent: bool = False) -> str:
        if value is None:
            return "—"
        return f"{value * 100:.1f}%" if percent else f"{value:g}"

    for combo in comparison["combinations"]:
        cost = f"${combo['cost']['total_cost_usd']:.4f}" if combo["cost"]["known"] else "未知"
        token_flag = "（token 预算不受支持）" if combo["token_budget_unsupported"] else ""
        lines.append(
            f"| {combo['model']} | {combo['strategy']} | {combo['repeat']} "
            f"| {combo['denominator']['total']} | {combo['denominator']['completed']} "
            f"| {combo['denominator']['budget_exhausted']} "
            f"| {_fmt(combo['formal']['rate'], True)} ({combo['formal']['solved']}/{combo['formal']['evaluable']}) "
            f"| {_fmt(combo['sample_validation']['rate'], True)} "
            f"| {_fmt(combo['fix_rate']['rate'], True)} "
            f"| {_fmt(combo['actual_consumption']['avg_calls_per_problem'])} "
            f"| {_fmt(combo['actual_consumption']['avg_tokens_per_problem'])} "
            f"| {cost}{token_flag} |"
        )
    lines.append("")

    lines.append("## 跨重复稳定性")
    lines.append("")
    for agg in comparison["by_model_strategy"]:
        lines.append(f"- **{agg['model']} × {agg['strategy']}**：{agg['uncertainty_note']}")
        for dotted, rng in agg["ranges"].items():
            lines.append(
                f"  - {dotted}：{_fmt(rng['min'], 'rate' in dotted)} ~ {_fmt(rng['max'], 'rate' in dotted)}"
            )
    lines.append("")

    lines.append("## 按难度与标签")
    lines.append("")
    for combo in comparison["combinations"]:
        lines.append(f"### {combo['model']} × {combo['strategy']} × r{combo['repeat']}")
        lines.append("")
        for label, groups in (
            ("难度", combo["by_difficulty"]),
            ("标签", combo["by_tags"]),
        ):
            parts = [
                f"{name}: {stats['solved']}/{stats['total']} ({_fmt(stats['rate'], True)})"
                for name, stats in groups.items()
            ]
            lines.append(f"- {label}：{'；'.join(parts) if parts else '无数据'}")
        lines.append("")

    error_analysis = comparison.get("error_analysis")
    if error_analysis:
        lines.append("## 错误分析")
        lines.append("")
        total = error_analysis.get("total_failures", 0)
        counts = "；".join(
            f"{name}: {count}"
            for name, count in error_analysis.get("categories", {}).items()
            if count
        )
        lines.append(f"- 失败总数：{total}（{counts or '无失败'}）")
        top = error_analysis.get("top_patterns", [])
        if top:
            lines.append("")
            lines.append("| 高频错误模式 | 次数 |")
            lines.append("|---|---:|")
            for entry in top:
                pattern = entry["pattern"].replace("|", "\\|")
                lines.append(f"| {pattern} | {entry['count']} |")
        for category, hints in error_analysis.get("suggestions", {}).items():
            lines.append(f"- **{category} 修复建议**：{'；'.join(hints)}")
        lines.append("")

    lines.append(
        f"> 生成时间：{comparison['generated_at']}；未知成本表示模型定价未配置，不代表 $0。"
    )
    lines.append("")
    return "\n".join(lines)


def _majority_solved(
    problem_ids: List[str],
    raw_results: Dict[str, List[Dict[str, Any]]],
    model_combos: List[Dict[str, Any]],
) -> Dict[str, bool]:
    """Per-problem majority outcome across a model's repeats.

    ``budget_exhausted`` counts as not solved; a problem is solved only when
    the majority of the model's repeats finished it successfully.
    """
    per_repeat: Dict[int, Dict[str, bool]] = {}
    for combo in model_combos:
        for result in raw_results.get(combo["combo_id"], []):
            record = per_repeat.setdefault(combo["repeat"], {})
            record[result.get("problem_id")] = result.get("status") == "success"
    total = len(per_repeat.values())
    return {
        problem_id: sum(1 for rep in per_repeat.values() if rep.get(problem_id)) > total / 2
        for problem_id in problem_ids
    }


def _mcnemar_annotation(wins: int, losses: int) -> Dict[str, Any]:
    """Exact McNemar annotation over discordant pairs (wins, losses).

    Two-sided exact binomial p-value: 2 * P(X <= min(wins, losses)) under
    H0 with p=0.5 — identical to scipy's ``binomtest`` without the import.
    """
    discordant = wins + losses
    if discordant == 0:
        return {
            "discordant_pairs": 0,
            "p_value": None,
            "significant": None,
            "note": "样本不足，无法检验",
        }
    tail = sum(comb(discordant, k) for k in range(0, min(wins, losses) + 1))
    p_value = min(1.0, 2.0 * tail / 2**discordant)
    note = "样本量较小，结论保守" if discordant < 5 else ""
    return {
        "discordant_pairs": discordant,
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
        "note": note,
    }


def build_model_comparison(
    meta: Dict[str, Any],
    combos: List[Dict[str, Any]],
    raw_results: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Cross-model analysis: win-rate matrix, significance, cost-effectiveness."""
    problem_ids = list(meta.get("dataset", {}).get("problem_ids", []))
    by_strategy: Dict[str, List[Dict[str, Any]]] = {}
    for combo in combos:
        by_strategy.setdefault(combo["strategy"], []).append(combo)

    strategies: Dict[str, Any] = {}
    for strategy in sorted(by_strategy):
        members = by_strategy[strategy]
        models = sorted({member["model"] for member in members})
        solved = {
            model: _majority_solved(
                problem_ids,
                raw_results,
                [m for m in members if m["model"] == model],
            )
            for model in models
        }

        matrix = []
        significance = []
        for a in models:
            cells: Dict[str, Any] = {}
            for b in models:
                if a == b:
                    continue
                wins = ties = losses = 0
                for problem_id in problem_ids:
                    solved_a = solved[a][problem_id]
                    solved_b = solved[b][problem_id]
                    if solved_a and not solved_b:
                        wins += 1
                    elif solved_b and not solved_a:
                        losses += 1
                    else:
                        ties += 1
                cells[b] = {
                    "wins": wins,
                    "ties": ties,
                    "losses": losses,
                    "win_rate": _rate(wins, wins + ties + losses),
                }
                if a < b:
                    # Wins of b against a are the losses recorded from a's view
                    annotation = _mcnemar_annotation(wins, losses)
                    annotation.update({"a": a, "b": b})
                    significance.append(annotation)
            matrix.append({"model": a, "solved": sum(solved[a].values()), "against": cells})
        strategies[strategy] = {"matrix": matrix, "significance": significance}

    # Cost-effectiveness per model across all its combinations
    per_model: Dict[str, Dict[str, Any]] = {}
    for combo in combos:
        entry = per_model.setdefault(combo["model"], {"solved": 0, "cost": 0.0, "known": True})
        entry["solved"] += combo["solved"]
        if not combo["cost"]["known"]:
            entry["known"] = False
        else:
            entry["cost"] += combo["cost"]["total_cost_usd"] or 0.0

    ranked = []
    unknown_models = []
    for model, entry in sorted(per_model.items()):
        if not entry["known"] or entry["cost"] <= 0:
            unknown_models.append(model)
            continue
        ranked.append(
            {
                "model": model,
                "solved": entry["solved"],
                "total_cost_usd": round(entry["cost"], 6),
                "solved_per_usd": round(entry["solved"] / entry["cost"], 3),
            }
        )
    ranked.sort(key=lambda item: item["solved_per_usd"], reverse=True)

    return {
        "strategies": strategies,
        "cost_effectiveness": ranked,
        "cost_unknown_models": unknown_models,
    }


def generate_comparison_report(exp_dir: Path) -> Dict[str, Any]:
    meta = _load_json(Path(exp_dir) / "experiment.json")
    combos: List[Dict[str, Any]] = []
    raw_results: Dict[str, List[Dict[str, Any]]] = {}
    for combo_ref in meta.get("combinations", []):
        combo_dir = Path(exp_dir) / combo_ref["combo_dir"]
        summary = _load_json(combo_dir / "summary.json")
        results = _load_json(combo_dir / f"{combo_ref['strategy']}_results.json")
        ledger = _load_json(combo_dir / "budget_ledger.json")
        raw_results[combo_ref["combo_id"]] = results
        combos.append(_combo_metrics(meta, combo_ref, summary, results, ledger))

    problem_info = {
        problem["problem_id"]: problem for problem in meta.get("dataset", {}).get("problems", [])
    }
    for combo in combos:
        combo["error_analysis"] = analyze_results(raw_results[combo["combo_id"]], problem_info)

    comparison = {
        "generated_at": datetime.now().isoformat(),
        "experiment": meta,
        "combinations": combos,
        "by_model_strategy": _aggregate_by_model_strategy(combos),
        "model_comparison": build_model_comparison(meta, combos, raw_results),
        "error_analysis": analyze_results(
            [r for results in raw_results.values() for r in results], problem_info
        ),
    }

    with open(Path(exp_dir) / "comparison.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
        f.write("\n")

    if combos:
        fieldnames = list(_flat_csv_row(combos[0]).keys())
        with open(Path(exp_dir) / "comparison.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for combo in combos:
                writer.writerow(_flat_csv_row(combo))

    with open(Path(exp_dir) / "REPORT.md", "w", encoding="utf-8") as f:
        f.write(_render_markdown(comparison))

    logger.info(
        "comparison_report_generated",
        experiment_id=meta.get("experiment_id"),
        combinations=len(combos),
    )
    return comparison
