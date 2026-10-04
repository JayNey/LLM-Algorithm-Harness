"""
Evolution Analysis Report Generation

This module provides functions to generate evolution analysis sections
for multi-round strategy reports.
"""

from pathlib import Path

from src.models import ExecutionResult


def generate_evolution_section(result: ExecutionResult, output_dir: Path | None = None) -> str:
    """
    Generate markdown section for code quality evolution analysis.

    Args:
        result: Execution result with iteration data
        output_dir: Optional directory to save evolution chart

    Returns:
        Markdown string for evolution section, or empty string if not applicable
    """
    # Only generate for multi-round strategies with quality data
    if len(result.iterations) < 2:
        return ""

    # Check if any iteration has quality data
    has_quality_data = any(
        iter_result.code_quality is not None for iter_result in result.iterations
    )

    if not has_quality_data:
        return ""

    try:
        from src.analysis.evolution import EvolutionAnalyzer

        analyzer = EvolutionAnalyzer(result)

        # Generate text report
        report_text = analyzer.generate_evolution_report()

        # Generate chart if output directory provided
        chart_section = ""
        if output_dir is not None:
            chart_path = output_dir / f"{result.problem_id}_evolution.png"
            try:
                analyzer.generate_evolution_chart(chart_path)
                chart_section = f"\n### 演化趋势图表\n\n![质量演化]({chart_path.name})\n"
            except Exception:
                # Chart generation is optional, don't fail if it errors
                pass

        return f"\n{report_text}\n{chart_section}"

    except Exception:
        # Don't fail report generation if evolution analysis fails
        return ""


def should_include_evolution_analysis(result: ExecutionResult) -> bool:
    """
    Check if evolution analysis should be included for this result.

    Args:
        result: Execution result

    Returns:
        True if evolution analysis is applicable
    """
    # Need at least 2 iterations
    if len(result.iterations) < 2:
        return False

    # Need at least one iteration with quality data
    return any(iter_result.code_quality is not None for iter_result in result.iterations)
