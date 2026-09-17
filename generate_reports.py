#!/usr/bin/env python3
"""
Generate evaluation reports from summary.json files.

Usage:
    python generate_reports.py [summary.json] [output_dir]

Examples:
    # Auto-find latest summary.json and output to reports/
    python generate_reports.py

    # Specify summary.json path
    python generate_reports.py results/my_evaluation/summary.json

    # Specify custom output directory
    python generate_reports.py results/my_evaluation/summary.json custom_reports/
"""

import json
import sys
from pathlib import Path

from src.reporting.html_generator import HTMLGenerator
from src.reporting.markdown_generator import MarkdownGenerator
from src.reporting.csv_exporter import CSVExporter
from src.models import ExecutionResult


def find_latest_summary() -> Path:
    """
    Find the most recent summary.json file in results/ directory.

    Returns:
        Path to latest summary.json

    Raises:
        FileNotFoundError: If no summary.json found
    """
    results_dir = Path("results")
    if not results_dir.exists():
        raise FileNotFoundError("results/ directory not found")

    # Find all summary.json files (both in subdirs and root)
    summary_files = list(results_dir.glob("*/summary.json"))

    # Also check for summary.json directly in results/
    root_summary = results_dir / "summary.json"
    if root_summary.exists():
        summary_files.append(root_summary)

    if not summary_files:
        raise FileNotFoundError("No summary.json files found in results/")

    # Return the most recently modified
    latest = max(summary_files, key=lambda p: p.stat().st_mtime)
    return latest


def generate_reports(summary_path: str = None, output_dir: str = None):
    """
    Generate HTML and Markdown reports from a summary.json file.

    Args:
        summary_path: Path to summary.json file (auto-finds latest if None)
        output_dir: Optional output directory (defaults to reports/)
    """
    # Auto-find latest summary.json if not specified
    if summary_path is None:
        try:
            summary_file = find_latest_summary()
            print(f"Auto-detected: {summary_file}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
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
    # Handle both old format (metrics/results) and new format (strategies)
    if "strategies" in data:
        # New format: {"strategies": {"strategy_name": {...}}}
        metrics = data["strategies"]
        # Load individual result files
        results = {}
        results_dir = summary_file.parent
        for strategy_name in metrics.keys():
            result_file = results_dir / f"{strategy_name}_results.json"
            if result_file.exists():
                with open(result_file, 'r') as f:
                    strategy_data = json.load(f)
                    # Convert to ExecutionResult objects
                    results[strategy_name] = [
                        ExecutionResult(**r) for r in strategy_data
                    ]
            else:
                results[strategy_name] = []
    else:
        # Old format: {"metrics": {...}, "results": {...}}
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

    # Generate CSV export
    if results:
        csv_path = out_dir / "evaluation_results.csv"
        CSVExporter.export_all(results, str(csv_path))
        print(f"✓ Generated CSV export: {csv_path}")

    print(f"\nReports generated successfully in: {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        sys.exit(0)

    summary_path = sys.argv[1] if len(sys.argv) > 1 else None
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    generate_reports(summary_path, output_dir)
