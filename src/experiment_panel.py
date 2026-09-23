"""
Interactive HTML comparison panel for experiments (issue #48).

Renders ``panel.html`` from ``comparison.json`` using Chart.js loaded from a
CDN (no self-built chart engine): a radar for multi-dimension capability, a
scatter for cost vs accuracy, and a bar chart for side-by-side consumption,
plus win-rate matrix tables. Chart data is embedded as JSON so the panel is
one self-contained file; without network access the charts degrade to a
visible hint instead of silently rendering nothing.
"""

import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List

from src.utils.logging import get_logger

logger = get_logger(__name__)


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _rate(value: Any) -> float:
    return round(value, 4) if isinstance(value, (int, float)) else 0.0


def _build_panel_data(comparison: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the chart payloads consumed by the embedded page script."""
    combos = comparison.get("combinations", [])
    model_comparison = comparison.get("model_comparison", {})
    strategies = model_comparison.get("strategies", {})
    cost_ranking = {
        entry["model"]: entry["solved_per_usd"]
        for entry in model_comparison.get("cost_effectiveness", [])
    }
    max_ratio = max(cost_ranking.values()) if cost_ranking else 0.0

    radar: Dict[str, Any] = {
        "labels": ["隐藏通过率", "样例验证率", "修复率", "成本效益"],
        "datasets": [],
    }
    scatter: List[Dict[str, Any]] = []
    bar = {"labels": [], "calls": [], "elapsed": [], "tokens": []}

    for combo in combos:
        label = f"{combo['model']} × {combo['strategy']}"
        cost_ratio = cost_ranking.get(combo["model"])
        radar["datasets"].append(
            {
                "label": label,
                "values": [
                    _rate(combo["formal"]["rate"]),
                    _rate(combo["sample_validation"]["rate"]),
                    _rate(combo["fix_rate"]["rate"]),
                    round(cost_ratio / max_ratio, 4) if cost_ratio and max_ratio else 0.0,
                ],
            }
        )
        if combo["cost"]["known"] and (combo["cost"]["total_cost_usd"] or 0) > 0:
            scatter.append(
                {
                    "label": label,
                    "x": combo["cost"]["total_cost_usd"],
                    "y": _rate(combo["formal"]["rate"]),
                }
            )
        bar["labels"].append(label)
        bar["calls"].append(_rate(combo["actual_consumption"]["avg_calls_per_problem"]))
        bar["tokens"].append(_rate(combo["actual_consumption"]["avg_tokens_per_problem"]))
        bar["elapsed"].append(_rate(combo["actual_consumption"]["elapsed_seconds"]))

    matrix_tables = []
    for strategy, payload in strategies.items():
        rows = []
        for row in payload.get("matrix", []):
            cells = []
            for opponent, cell in row.get("against", {}).items():
                cells.append(
                    {
                        "opponent": opponent,
                        "text": (
                            f"{cell['wins']}胜 {cell['ties']}平 {cell['losses']}负"
                            f"（{round(cell['win_rate'] * 100, 1)}%）"
                            if cell["win_rate"] is not None
                            else "—"
                        ),
                    }
                )
            rows.append({"model": row["model"], "solved": row["solved"], "cells": cells})
        matrix_tables.append(
            {"strategy": strategy, "rows": rows, "significance": payload.get("significance", [])}
        )

    return {
        "experiment_id": comparison.get("experiment", {}).get("experiment_id", ""),
        "name": comparison.get("experiment", {}).get("name"),
        "radar": radar,
        "scatter": scatter,
        "bar": bar,
        "matrix_tables": matrix_tables,
        "cost_unknown_models": model_comparison.get("cost_unknown_models", []),
        "error_categories": [
            {"label": name, "count": count}
            for name, count in (
                comparison.get("error_analysis", {}).get("categories") or {}
            ).items()
            if count
        ],
        "generated_at": comparison.get("generated_at") or datetime.now().isoformat(),
    }


def _render_panel(data: Dict[str, Any]) -> str:
    """Render the self-contained panel page around the embedded data."""
    embedded = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    matrix_html: List[str] = []
    for table in data["matrix_tables"]:
        rows = table["rows"]
        if rows:
            header = (
                "<tr><th>模型（解出）</th>"
                + "".join(f"<th>vs {escape(cell['opponent'])}</th>" for cell in rows[0]["cells"])
                + "</tr>"
            )
            body = "".join(
                "<tr><th>"
                + escape(f"{row['model']}（解出 {row['solved']}）")
                + "</th>"
                + "".join(f"<td>{escape(cell['text'])}</td>" for cell in row["cells"])
                + "</tr>"
                for row in rows
            )
            table_tag = f'<table class="matrix">{header}{body}</table>'
        else:
            table_tag = "<p>无对比数据</p>"
        sig_lines = "".join(
            f"<li>{escape(item['a'])} vs {escape(item['b'])}："
            + (
                f"p={item['p_value']}，{'显著' if item['significant'] else '不显著'}"
                if item.get("p_value") is not None
                else escape(item.get("note") or "样本不足，无法检验")
            )
            + (f"（{escape(item['note'])}）" if item.get("note") else "")
            + "</li>"
            for item in table.get("significance", [])
        )
        matrix_html.append(
            f"<section><h2>胜率矩阵 — {escape(table['strategy'])}</h2>"
            + table_tag
            + (f'<ul class="sig">{sig_lines}</ul>' if sig_lines else "")
            + "</section>"
        )

    return (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        "<title>模型对比分析面板</title>\n"
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>\n'
        "<style>\n"
        "body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;margin:24px;color:#1f2328}\n"
        "h1{font-size:20px} h2{font-size:16px;margin-top:28px}\n"
        ".charts{display:flex;flex-wrap:wrap;gap:24px}.chart-box{width:420px;height:320px}\n"
        "table.matrix{border-collapse:collapse;margin-top:8px}\n"
        "table.matrix th,table.matrix td{border:1px solid #d0d7de;padding:6px 10px;font-size:14px;text-align:left}\n"
        ".sig{font-size:13px;color:#57606a}\n"
        ".unknown{color:#9a6700;font-size:13px}\n"
        "#offline-hint{display:none;background:#fff8c5;border:1px solid #d4a72c;padding:8px 12px;margin:12px 0}\n"
        "</style>\n</head>\n<body>\n"
        f"<h1>模型对比分析面板 — {escape(data['name'] or data['experiment_id'])}</h1>\n"
        f"<p>实验：{escape(data['experiment_id'])} · 生成时间：{escape(data['generated_at'])}</p>\n"
        '<div id="offline-hint">图表库（Chart.js CDN）未加载：当前离线或 CDN 不可达，表格数据仍可阅读。</div>\n'
        f"<p class=\"unknown\">成本未知模型：{escape('、'.join(data['cost_unknown_models'])) or '无'}"
        "（不进入成本散点图与成本效益排名）</p>\n"
        '<div class="charts">\n'
        '<div><h2>能力雷达图</h2><div class="chart-box"><canvas id="radar"></canvas></div></div>\n'
        '<div><h2>成本 vs 准确率</h2><div class="chart-box"><canvas id="scatter"></canvas></div></div>\n'
        '<div><h2>消耗并排对比</h2><div class="chart-box"><canvas id="bar"></canvas></div></div>\n'
        '<div><h2>错误类别占比</h2><div class="chart-box"><canvas id="error-pie"></canvas></div></div>\n'
        "</div>\n"
        + "".join(matrix_html)
        + '\n<script id="panel-data" type="application/json">'
        + embedded
        + "</script>\n"
        "<script>\n"
        "const DATA = JSON.parse(document.getElementById('panel-data').textContent);\n"
        "if (!window.Chart) { document.getElementById('offline-hint').style.display = 'block'; }\n"
        "else {\n"
        "  new Chart(document.getElementById('radar'), {type: 'radar', data: {labels: DATA.radar.labels,"
        " datasets: DATA.radar.datasets.map(d => ({label: d.label, data: d.values, fill: false}))}});\n"
        "  new Chart(document.getElementById('scatter'), {type: 'scatter', data: {datasets: [{"
        " label: '模型×策略（成本已知）', data: DATA.scatter, pointRadius: 6}]},"
        " options: {scales: {x: {title: {display: true, text: '总成本 (USD)'}}, y: {title: {display: true, text: '隐藏通过率'}, min: 0, max: 1}}}});\n"
        "  new Chart(document.getElementById('bar'), {type: 'bar', data: {labels: DATA.bar.labels,"
        " datasets: [{label: '平均调用数', data: DATA.bar.calls}, {label: '平均耗时(秒)', data: DATA.bar.elapsed},"
        " {label: '平均 tokens', data: DATA.bar.tokens, yAxisID: 'y1'}]},"
        " options: {scales: {y1: {position: 'right'}}}});\n"
        "  if (DATA.error_categories.length) { new Chart(document.getElementById('error-pie'),"
        " {type: 'doughnut', data: {labels: DATA.error_categories.map(e => e.label),"
        " datasets: [{data: DATA.error_categories.map(e => e.count)}]}}); }\n"
        "}\n</script>\n</body>\n</html>\n"
    )


def generate_html_panel(exp_dir: Path) -> Path:
    """Generate ``panel.html`` next to ``comparison.json``."""
    exp_dir = Path(exp_dir)
    comparison = _load_json(exp_dir / "comparison.json")
    data = _build_panel_data(comparison)
    panel_path = exp_dir / "panel.html"
    with open(panel_path, "w", encoding="utf-8") as f:
        f.write(_render_panel(data))
    logger.info("panel_generated", experiment_id=data.get("experiment_id"), path=str(panel_path))
    return panel_path
