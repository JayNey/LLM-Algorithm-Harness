#!/usr/bin/env python3
"""
Generate evaluation reports from summary.json files.

Usage:
    python generate_reports.py <summary.json> [output_dir]

Examples:
    # Generate reports in default reports/ directory
    python generate_reports.py results/my_evaluation/summary.json

    # Generate reports in custom directory
    python generate_reports.py results/my_evaluation/summary.json custom_reports/
"""

import json
import sys
from pathlib import Path

from src.reporting.html_generator import HTMLGenerator
from src.reporting.markdown_generator import MarkdownGenerator


def generate_reports(summary_path: str, output_dir: str = None):
    """
    Generate HTML and Markdown reports from a summary.json file.

    Args:
        summary_path: Path to summary.json file
        output_dir: Optional output directory (defaults to reports/)
    """
    summary_file = Path(summary_path)

    if not summary_file.exists():
        print(f"Error: Summary file not found: {summary_path}")
        sys.exit(1)

    # Load summary data
    with open(summary_file, 'r') as f:
        data = json.load(f)

    # Determine output directory
    if output_dir:
        out_dir = Path(output_dir)
    else:
        # Default to reports/ directory
        out_dir = Path("reports")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Extract data from summary
    metrics = data.get("metrics", {})
    results = data.get("results", {})
    config = data.get("config", {})

    # Generate HTML report
    html_path = out_dir / "evaluation_report.html"
    HTMLGenerator.generate(
        metrics=metrics,
        results=results,
        output_path=str(html_path),
        include_charts=True,
        config=config,
    )
    print(f"✓ Generated HTML report: {html_path}")

    # Generate Markdown report
    md_path = out_dir / "evaluation_report.md"
    MarkdownGenerator.generate(
        metrics=metrics,
        results=results,
        output_path=str(md_path),
        config=config,
    )
    print(f"✓ Generated Markdown report: {md_path}")

    print(f"\nReports generated successfully in: {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    summary_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    generate_reports(summary_path, output_dir)
