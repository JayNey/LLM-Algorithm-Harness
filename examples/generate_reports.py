#!/usr/bin/env python3
"""
Example script demonstrating how to use the reporting module.

This script shows how to:
1. Load real evaluation results from the results/ directory
2. Calculate metrics
3. Generate reports in multiple formats (CSV, Markdown, HTML with charts)

Usage:
    python3 examples/generate_reports.py                       # use results/, output to reports/
    python3 examples/generate_reports.py --results-dir results --output reports
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from typing import Dict, List

from src.models import ExecutionResult
from src.reporting import CSVExporter, MarkdownGenerator, ChartGenerator, HTMLGenerator


def load_results_from_dir(results_dir: str) -> Dict[str, List[ExecutionResult]]:
    """
    Load evaluation results from a harness output directory.

    Accepts either a run directory containing ``<strategy>_results.json``
    files, or the base results directory (picks the run named by
    ``latest.json``). Strategies are keyed by the ``strategy`` field of
    the records.
    """
    dir_path = Path(results_dir)
    files = sorted(dir_path.glob("*_results.json"))

    if not files:
        latest_file = dir_path / "latest.json"
        if latest_file.exists():
            with open(latest_file, "r", encoding="utf-8") as f:
                latest = json.load(f).get("latest_run")
            if latest:
                dir_path = dir_path / latest
                files = sorted(dir_path.glob("*_results.json"))

    if not files:
        raise FileNotFoundError(
            f"No *_results.json files found in {dir_path}. "
            "Run an evaluation first, e.g.: "
            "python3 -m src.main --dataset data/problems.json --config config.json"
        )

    print(f"Using run directory: {dir_path}")

    results: Dict[str, List[ExecutionResult]] = {}
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for result_data in data:
            strategy = result_data.get("strategy", path.stem.replace("_results", ""))
            results.setdefault(strategy, []).append(ExecutionResult(**result_data))

    return results


def load_model_name(config_path: str = "config.json") -> str:
    """Read the model name from config.json (never touches the API key)."""
    path = Path(config_path)
    if not path.exists():
        return "unknown"
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config.get("llm_config", {}).get("model", "unknown")


def calculate_metrics(results: Dict[str, List[ExecutionResult]]) -> Dict[str, Dict]:
    """
    Calculate metrics for each strategy.

    Returns:
        Dictionary mapping strategy name to metrics dict
    """
    metrics = {}

    for strategy_name, strategy_results in results.items():
        total = len(strategy_results)
        solved = sum(1 for r in strategy_results if r.is_successful())
        total_tokens = sum(r.total_tokens for r in strategy_results)

        metrics[strategy_name] = {
            'total_problems': total,
            'solved_problems': solved,
            'success_rate': solved / total if total > 0 else 0,
            'avg_tokens_per_problem': total_tokens / total if total > 0 else 0,
        }

    return metrics


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Generate visualization reports from real evaluation results"
    )
    parser.add_argument(
        "--results-dir", type=str, default="results",
        help="Directory containing <strategy>_results.json files (default: results)"
    )
    parser.add_argument(
        "--output", type=str, default="reports",
        help="Output directory for generated reports (default: reports)"
    )
    args = parser.parse_args()

    print(f"Loading evaluation results from {args.results_dir}/ ...")
    results = load_results_from_dir(args.results_dir)
    for strategy, strategy_results in sorted(results.items()):
        print(f"  {strategy}: {len(strategy_results)} problems")
    metrics = calculate_metrics(results)

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating reports in {output_dir}/")

    # 1. Generate CSV export
    print("  [1/4] Generating CSV export...")
    csv_path = output_dir / "results.csv"
    CSVExporter.export_all(results, str(csv_path))
    print(f"        ✓ Saved to {csv_path}")

    # 2. Generate Markdown report
    print("  [2/4] Generating Markdown report...")
    md_path = output_dir / "report.md"
    MarkdownGenerator.generate(metrics, results, str(md_path))
    print(f"        ✓ Saved to {md_path}")

    # 3. Generate individual charts
    print("  [3/4] Generating charts...")

    chart_dir = output_dir / "charts"
    chart_dir.mkdir(exist_ok=True)

    # Success rate chart
    success_chart = ChartGenerator.generate_success_rate_chart(metrics)
    with open(chart_dir / "success_rate.png", "wb") as f:
        f.write(success_chart.read())
    print(f"        ✓ Success rate chart: {chart_dir}/success_rate.png")

    # Token consumption chart
    token_chart = ChartGenerator.generate_token_chart(metrics)
    with open(chart_dir / "token_consumption.png", "wb") as f:
        f.write(token_chart.read())
    print(f"        ✓ Token chart: {chart_dir}/token_consumption.png")

    # Iteration distribution
    iter_chart = ChartGenerator.generate_iteration_distribution(results)
    if iter_chart:
        with open(chart_dir / "iteration_dist.png", "wb") as f:
            f.write(iter_chart.read())
        print(f"        ✓ Iteration distribution: {chart_dir}/iteration_dist.png")
    else:
        print(f"        ℹ Iteration distribution skipped (all single-round)")

    # 4. Generate self-contained HTML report
    print("  [4/4] Generating HTML report...")
    html_path = output_dir / "report.html"
    HTMLGenerator.generate(
        metrics=metrics,
        results=results,
        output_path=str(html_path),
        include_charts=True,
        config={
            'model': load_model_name(),
            'temperature': 0.7,
            'timeout': 300
        }
    )
    print(f"        ✓ Saved to {html_path}")

    print(f"\n✅ All reports generated successfully!")
    print(f"\n📊 Open {html_path} in your browser to view the interactive report.")


if __name__ == "__main__":
    main()

