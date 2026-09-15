#!/usr/bin/env python3
"""
Generate reports from evaluation results.

Usage:
    python3 generate_reports.py [--results-dir RESULTS_DIR] [--output-dir OUTPUT_DIR]

This script:
1. Loads evaluation results from the results directory
2. Generates HTML, Markdown, and CSV reports with charts
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.models import ExecutionResult
from src.reporting import CSVExporter, MarkdownGenerator, HTMLGenerator


def load_results_from_directory(results_dir: str) -> Dict[str, List[ExecutionResult]]:
    """
    Load all strategy results from directory.

    Args:
        results_dir: Directory containing *_results.json files

    Returns:
        Dictionary mapping strategy name to list of ExecutionResults
    """
    results_path = Path(results_dir)

    if not results_path.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    results = {}

    # Find all *_results.json files
    for result_file in results_path.glob("*_results.json"):
        strategy_name = result_file.stem.replace("_results", "")

        print(f"Loading {strategy_name} results from {result_file.name}...")

        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Convert to ExecutionResult objects
        if isinstance(data, list) and len(data) > 0:
            results[strategy_name] = [
                ExecutionResult(**item) for item in data
            ]
            print(f"  Loaded {len(results[strategy_name])} results for {strategy_name}")

    if not results:
        print(f"\n⚠️  No result files found in {results_dir}")
        print("Expected files like: vanilla_results.json, chain_of_thought_results.json, etc.")
        sys.exit(1)

    return results


def load_summary(results_dir: str) -> Dict:
    """Load summary.json if it exists."""
    summary_path = Path(results_dir) / "summary.json"

    if summary_path.exists():
        with open(summary_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    return {}


def calculate_metrics(results: Dict[str, List[ExecutionResult]]) -> Dict[str, Dict]:
    """
    Calculate metrics for each strategy.

    Returns:
        Dictionary mapping strategy name to metrics dict
    """
    metrics = {}

    for strategy_name, strategy_results in results.items():
        if not strategy_results:
            continue

        total = len(strategy_results)
        solved = sum(1 for r in strategy_results if r.is_successful())
        total_tokens = sum(r.total_tokens for r in strategy_results)
        total_attempts = sum(len(r.iterations) for r in strategy_results)

        metrics[strategy_name] = {
            'total_problems': total,
            'solved_problems': solved,
            'success_rate': solved / total if total > 0 else 0,
            'avg_tokens_per_problem': total_tokens / total if total > 0 else 0,
            'avg_attempts_per_problem': total_attempts / total if total > 0 else 0,
        }

    return metrics


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Generate evaluation reports from results directory"
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="./results",
        help="Directory containing evaluation results (default: ./results)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./reports",
        help="Output directory for generated reports (default: ./reports)"
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Skip chart generation in HTML report"
    )

    args = parser.parse_args()

    print("="*60)
    print("Report Generator")
    print("="*60)
    print()

    # Load results
    try:
        results = load_results_from_directory(args.results_dir)
        summary = load_summary(args.results_dir)
    except Exception as e:
        print(f"❌ Error loading results: {e}")
        sys.exit(1)

    # Calculate metrics
    print("\nCalculating metrics...")
    metrics = calculate_metrics(results)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📊 Generating reports in {output_dir}/")
    print()

    # 1. Generate CSV export
    print("  [1/3] Generating CSV export...")
    csv_path = output_dir / "results.csv"
    try:
        CSVExporter.export_all(results, str(csv_path))
        print(f"        ✓ Saved to {csv_path}")
    except Exception as e:
        print(f"        ✗ Error: {e}")

    # 2. Generate Markdown report
    print("  [2/3] Generating Markdown report...")
    md_path = output_dir / "report.md"
    try:
        MarkdownGenerator.generate(metrics, results, str(md_path))
        print(f"        ✓ Saved to {md_path}")
    except Exception as e:
        print(f"        ✗ Error: {e}")

    # 3. Generate HTML report
    print("  [3/3] Generating HTML report...")
    html_path = output_dir / "report.html"
    try:
        # Extract config from summary if available
        config = summary.get('config', {})

        HTMLGenerator.generate(
            metrics=metrics,
            results=results,
            output_path=str(html_path),
            include_charts=not args.no_charts,
            config=config
        )
        print(f"        ✓ Saved to {html_path}")
    except Exception as e:
        print(f"        ✗ Error: {e}")

    print()
    print("="*60)
    print("✅ Report generation complete!")
    print("="*60)
    print()
    print("📁 Generated files:")
    print(f"   • CSV:      {csv_path}")
    print(f"   • Markdown: {md_path}")
    print(f"   • HTML:     {html_path}")
    print()
    print(f"📊 Open {html_path} in your browser to view the interactive report.")


if __name__ == "__main__":
    main()
