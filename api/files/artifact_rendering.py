"""Render versioned, truthful evaluation snapshots without synthesizing domain results."""

from __future__ import annotations

import csv
import html
import io
import json
import zipfile
from typing import Any

from fastapi import HTTPException

from src.models import NOT_EVALUABLE
from src.reporting.chart_generator import ChartGenerator


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def _safe(value: str) -> str:
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r"))
        else value
    )


def render_snapshot(payload: dict[str, Any], format_name: str) -> tuple[str, str, bytes]:
    text = _json(payload)
    title = f"{'Complete' if payload['complete'] else 'Partial'} evaluation results - {payload['recorded_units']}/{payload['expected_units']} recorded units (revision {payload['revision']})"
    if format_name == "json":
        return "results.json", "application/json", text.encode("utf-8")
    if format_name in {"md", "markdown"}:
        escaped = text.replace("`", "\\u0060")
        return (
            "report.md",
            "text/markdown",
            (f"# {title}\n\n```json\n" + escaped + "```\n").encode("utf-8"),
        )
    if format_name == "html":
        return (
            "report.html",
            "text/html",
            (
                "<!doctype html><meta charset='utf-8'><title>Evaluation results</title><h1>"
                + html.escape(title)
                + "</h1><pre>"
                + html.escape(text)
                + "</pre>"
            ).encode("utf-8"),
        )
    if format_name == "csv":
        fields = [
            "revision",
            "state",
            "complete",
            "expected_units",
            "recorded_units",
            "problem_id",
            "strategy",
            "status",
            "metrics",
            "error_message",
            "execution",
        ]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for rows in payload["results"].values():
            for row in rows:
                values = {
                    **{key: payload[key] for key in fields[:5]},
                    **{key: row.get(key) for key in fields[5:]},
                }
                writer.writerow(
                    {
                        key: _safe(
                            ""
                            if value is None
                            else (
                                json.dumps(value, ensure_ascii=False, allow_nan=False)
                                if isinstance(value, (dict, list, bool))
                                else str(value)
                            )
                        )
                        for key, value in values.items()
                    }
                )
        return "results.csv", "text/csv", stream.getvalue().encode("utf-8-sig")
    if format_name == "png":
        metrics = {}
        for strategy, rows in payload["results"].items():
            if not rows:
                continue
            solved = sum(row["status"] == "success" for row in rows)
            total = sum(row["status"] != NOT_EVALUABLE for row in rows)
            metrics[strategy] = {
                "success_rate": solved / total if total else 0.0,
                "solved_problems": solved,
                "total_problems": total,
            }
        chart = ChartGenerator.generate_success_rate_chart(metrics, title=title)
        if chart is None:
            raise HTTPException(404, "Chart not available")
        try:
            return "success-rate.png", "image/png", chart.getvalue()
        finally:
            chart.close()
    if format_name == "zip":
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for kind in ("json", "csv", "markdown", "html", "png"):
                name, _, data = render_snapshot(payload, kind)
                bundle.writestr(name, data)
        return "results.zip", "application/zip", archive.getvalue()
    raise HTTPException(400, "Result format must be json, csv, markdown, html, png or zip")
