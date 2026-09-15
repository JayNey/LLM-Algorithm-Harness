#!/usr/bin/env python3
"""
Example script demonstrating how to use the reporting module.

This script shows how to:
1. Load evaluation results from JSON
2. Calculate metrics
3. Generate reports in multiple formats (CSV, Markdown, HTML with charts)
"""

import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from typing import Dict, List

from src.models import ExecutionResult
from src.reporting import CSVExporter, MarkdownGenerator, ChartGenerator, HTMLGenerator


def load_results_from_json(json_path: str) -> Dict[str, List[ExecutionResult]]:
    """
    Load evaluation results from JSON file.

    Expected JSON format:
    {
        "strategy_name": [
            {
                "problem_id": "two-sum",
                "success": true,
                "iterations": [...],
                ...
            },
            ...
        ]
    }
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = {}
    for strategy_name, result_list in data.items():
        results[strategy_name] = [
            ExecutionResult(**result_data) for result_data in result_list
        ]

    return results


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
    # Example: Load results from JSON
    # results_path = "results/evaluation_results.json"
    # results = load_results_from_json(results_path)

    # For demonstration, create sample data
    print("Creating sample evaluation data...")
    results = create_sample_data()
    metrics = calculate_metrics(results)

    # Create output directory
    output_dir = Path("examples/sample_reports")
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
            'model': 'gpt-4',
            'temperature': 0.7,
            'timeout': 300
        }
    )
    print(f"        ✓ Saved to {html_path}")

    print(f"\n✅ All reports generated successfully!")
    print(f"\n📊 Open {html_path} in your browser to view the interactive report.")


def create_sample_data() -> Dict[str, List[ExecutionResult]]:
    """Create sample evaluation data for demonstration."""
    from src.models import IterationResult, TestCaseResult

    # Strategy 1: Zero-shot
    zero_shot_results = [
        ExecutionResult(
            problem_id=f"problem-{i}",
            strategy="zero-shot",
            generated_code=f"def solution_{i}():\n    return {i}",
            status="success" if i % 3 != 0 else "failed",
            iterations=[
                IterationResult(
                    iteration=1,
                    prompt_tokens=100,
                    completion_tokens=50 + i * 10
                )
            ],
            test_results=[
                TestCaseResult(
                    test_case_index=j,
                    passed=i % 3 != 0,
                    actual_output="actual" if i % 3 != 0 else "wrong",
                    expected_output="expected",
                    error_message=None if i % 3 != 0 else "Test failed",
                    status="passed" if i % 3 != 0 else "wrong_answer"
                )
                for j in range(3)
            ],
            total_tokens=150 + i * 10,
            execution_time_seconds=0.5 + i * 0.1
        )
        for i in range(10)
    ]

    # Strategy 2: Few-shot
    few_shot_results = [
        ExecutionResult(
            problem_id=f"problem-{i}",
            strategy="few-shot",
            generated_code=f"def solution_{i}():\n    return {i * 2}",
            status="success" if i % 4 != 0 else "failed",
            iterations=[
                IterationResult(
                    iteration=1,
                    prompt_tokens=200,
                    completion_tokens=50 + i * 15
                )
            ],
            test_results=[
                TestCaseResult(
                    test_case_index=j,
                    passed=i % 4 != 0,
                    actual_output="actual" if i % 4 != 0 else "wrong",
                    expected_output="expected",
                    error_message=None if i % 4 != 0 else "Test failed",
                    status="passed" if i % 4 != 0 else "wrong_answer"
                )
                for j in range(3)
            ],
            total_tokens=250 + i * 15,
            execution_time_seconds=0.6 + i * 0.12
        )
        for i in range(10)
    ]

    # Strategy 3: Self-refine (multi-round)
    self_refine_results = []
    for i in range(10):
        success = i % 2 == 0
        iterations = [
            IterationResult(
                iteration=j + 1,
                prompt_tokens=150 + j * 20,
                completion_tokens=30 + i * 8 + j * 50
            )
            for j in range(3)  # 3 iterations
        ]

        self_refine_results.append(
            ExecutionResult(
                problem_id=f"problem-{i}",
                strategy="self-refine",
                generated_code=f"def solution_{i}_v3():\n    return {i ** 2}",
                status="success" if success else "failed",
                iterations=iterations,
                test_results=[
                    TestCaseResult(
                        test_case_index=j,
                        passed=success,
                        actual_output="actual" if success else "wrong",
                        expected_output="expected",
                        error_message=None if success else "Test failed after 3 iterations",
                        status="passed" if success else "wrong_answer"
                    )
                    for j in range(3)
                ],
                total_tokens=sum(it.prompt_tokens + it.completion_tokens for it in iterations),
                execution_time_seconds=1.5 + i * 0.2
            )
        )

    return {
        "zero-shot": zero_shot_results,
        "few-shot": few_shot_results,
        "self-refine": self_refine_results,
    }


if __name__ == "__main__":
    main()

