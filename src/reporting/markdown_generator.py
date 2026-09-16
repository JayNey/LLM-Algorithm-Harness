"""
Markdown report generation module.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.models import ExecutionResult
from src.utils.secrets import redact_sensitive_text


class MarkdownGenerator:
    """Generate Markdown format evaluation reports."""

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape special Markdown characters."""
        special_chars = ['*', '_', '|', '`', '[', ']']
        for char in special_chars:
            text = text.replace(char, f"\\{char}")
        return text

    @staticmethod
    def generate(
        metrics: Dict[str, Dict],
        results: Dict[str, List[ExecutionResult]],
        output_path: str,
        config: Dict = None
    ) -> str:
        """
        Generate Markdown evaluation report.

        Args:
            metrics: Dictionary mapping strategy name to metrics dict
            results: Dictionary mapping strategy name to results list
            output_path: Path to save the Markdown file
            config: Optional evaluation configuration dict

        Returns:
            Generated Markdown content
        """
        lines = []

        # Header
        lines.append("# LLM Algorithm Harness - Evaluation Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Configuration
        if config:
            lines.append("## Configuration")
            lines.append("")
            if "model" in config:
                lines.append(f"**Model:** {config['model']}")
            if "temperature" in config:
                lines.append(f"**Temperature:** {config['temperature']}")
            if "timeout" in config:
                lines.append(f"**Timeout:** {config['timeout']}s")
            if "max_iterations" in config:
                lines.append(f"**Max Iterations:** {config['max_iterations']}")
            lines.append("")

        # Overall metrics table
        lines.append("## Strategy Performance Summary")
        lines.append("")
        lines.append("| Strategy | Success Rate | Solved | Total | Avg Tokens | Avg Time (s) |")
        lines.append("|----------|-------------:|-------:|------:|-----------:|-------------:|")

        # Sort strategies by success rate
        sorted_strategies = sorted(
            metrics.items(),
            key=lambda x: x[1].get('success_rate', 0),
            reverse=True
        )

        for strategy_name, strategy_metrics in sorted_strategies:
            success_rate = strategy_metrics.get('success_rate', 0) * 100
            solved = strategy_metrics.get('solved_problems', 0)
            total = strategy_metrics.get('total_problems', 0)
            avg_tokens = strategy_metrics.get('avg_tokens_per_problem', 0)
            avg_time = strategy_metrics.get('avg_time_per_problem', 0)

            marker = " ⭐" if strategy_name == sorted_strategies[0][0] else ""
            lines.append(
                f"| {MarkdownGenerator._escape_markdown(strategy_name)}{marker} | "
                f"{success_rate:.1f}% | {solved} | {total} | "
                f"{avg_tokens:.0f} | {avg_time:.2f} |"
            )

        lines.append("")

        # Difficulty breakdown
        lines.append("## Performance by Difficulty")
        lines.append("")

        for strategy_name, strategy_metrics in sorted_strategies:
            by_difficulty = strategy_metrics.get('by_difficulty', {})
            if not by_difficulty:
                continue

            lines.append(f"### {MarkdownGenerator._escape_markdown(strategy_name)}")
            lines.append("")
            lines.append("| Difficulty | Success Rate | Solved | Total |")
            lines.append("|------------|-------------:|-------:|------:|")

            for difficulty in ['easy', 'medium', 'hard']:
                if difficulty in by_difficulty:
                    diff_data = by_difficulty[difficulty]
                    rate = diff_data.get('success_rate', 0) * 100
                    solved = diff_data.get('solved', 0)
                    total = diff_data.get('total', 0)
                    lines.append(f"| {difficulty.capitalize()} | {rate:.1f}% | {solved} | {total} |")

            lines.append("")

        # Failed cases
        lines.append("## Failed Cases")
        lines.append("")

        has_failures = False
        for strategy_name in sorted_strategies:
            strategy_name = strategy_name[0]
            strategy_results = results.get(strategy_name, [])
            failed = [r for r in strategy_results if not r.is_successful()]

            if failed:
                has_failures = True
                lines.append(f"### {MarkdownGenerator._escape_markdown(strategy_name)}")
                lines.append("")

                # Show first 10 failed cases with error messages
                shown_count = min(10, len(failed))
                for result in failed[:shown_count]:
                    error_msg = result.error_message or "Unknown error"
                    lines.append(f"- **{result.problem_id}**: {error_msg}")

                if len(failed) > 10:
                    lines.append(f"- ... and {len(failed) - 10} more")

                lines.append("")

        if not has_failures:
            lines.append("No failures recorded.")
            lines.append("")

        markdown_content = redact_sensitive_text("\n".join(lines))

        # Save to file
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        output_path_obj.write_text(markdown_content, encoding='utf-8')

        return markdown_content
