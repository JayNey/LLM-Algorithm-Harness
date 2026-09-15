"""
CSV export module for evaluation results.
"""

import csv
from pathlib import Path
from typing import Dict, List

from src.models import ExecutionResult


class CSVExporter:
    """Export evaluation results to CSV format."""

    @staticmethod
    def export(results: List[ExecutionResult], output_path: str) -> None:
        """
        Export a single strategy's results to CSV.

        Args:
            results: List of ExecutionResult objects
            output_path: Path to save the CSV file
        """
        # Create parent directories if needed
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Define CSV columns
        fieldnames = [
            "problem_id",
            "strategy",
            "status",
            "passed",
            "tokens",
            "time",
            "iterations",
            "error_message",
            "total_tests",
            "passed_tests",
            "failed_tests",
        ]

        # Write CSV with UTF-8 BOM for Excel compatibility
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                # Calculate test statistics
                total_tests = len(result.test_results)
                passed_tests = sum(1 for tc in result.test_results if tc.passed)
                failed_tests = total_tests - passed_tests

                # Calculate iteration count
                iteration_count = len(result.iterations) if result.iterations else 1

                row = {
                    "problem_id": result.problem_id,
                    "strategy": result.strategy,
                    "status": result.status,
                    "passed": result.is_successful(),
                    "tokens": result.total_tokens,
                    "time": round(result.execution_time_seconds, 3),
                    "iterations": iteration_count,
                    "error_message": result.error_message or "",
                    "total_tests": total_tests,
                    "passed_tests": passed_tests,
                    "failed_tests": failed_tests,
                }

                writer.writerow(row)

    @staticmethod
    def export_all(results_dict: Dict[str, List[ExecutionResult]], output_path: str) -> None:
        """
        Export multiple strategies' results to a single CSV.

        Args:
            results_dict: Dictionary mapping strategy name to results list
            output_path: Path to save the CSV file
        """
        # Merge all results into a single list
        all_results = []
        for strategy_name, results in results_dict.items():
            all_results.extend(results)

        # Use the single-strategy export method
        CSVExporter.export(all_results, output_path)
