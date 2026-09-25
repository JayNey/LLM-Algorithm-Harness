"""Learning curve report generation."""

from datetime import datetime
from pathlib import Path
from typing import Any

from src.benchmark.analysis import TrendAnalyzer
from src.benchmark.history import BenchmarkHistoryStorage
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """
    Generate comprehensive learning curve reports.

    Combines trend visualizations, statistical analysis, and version comparisons.
    """

    def __init__(self, storage: BenchmarkHistoryStorage, analyzer: TrendAnalyzer):
        """
        Initialize report generator.

        Args:
            storage: Benchmark history storage instance
            analyzer: Trend analyzer instance
        """
        self.storage = storage
        self.analyzer = analyzer

    def generate_report(
        self,
        model_ids: list[str],
        suite_name: str | None = None,
        output_path: str | Path | None = None,
        include_comparison: bool = True,
    ) -> Path:
        """
        Generate a comprehensive learning curve report.

        Args:
            model_ids: List of model IDs to include
            suite_name: Optional suite name filter
            output_path: Optional output path for report
            include_comparison: Whether to include model comparison

        Returns:
            Path to generated report file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output_path = Path("results/benchmark") / f"learning_curve_report_{timestamp}.md"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "generating_report",
            models=len(model_ids),
            suite=suite_name,
            output=str(output_path),
        )

        # Generate visualizations
        plots = []

        # Individual learning curves
        for model_id in model_ids:
            try:
                plot_path = self.analyzer.plot_learning_curve(
                    model_id, suite_name=suite_name
                )
                plots.append((model_id, plot_path))
            except ValueError as e:
                logger.warning("failed_to_plot_model", model=model_id, error=str(e))

        # Model comparison plot
        comparison_plot = None
        if include_comparison and len(model_ids) > 1:
            try:
                comparison_plot = self.analyzer.plot_model_comparison(
                    model_ids=model_ids, suite_name=suite_name
                )
            except ValueError as e:
                logger.warning("failed_to_plot_comparison", error=str(e))

        # Collect statistics
        model_stats = {}
        for model_id in model_ids:
            try:
                stats = self.analyzer.calculate_statistics(model_id, suite_name=suite_name)
                model_stats[model_id] = stats
            except ValueError as e:
                logger.warning("failed_to_calculate_stats", model=model_id, error=str(e))

        # Version comparison
        version_comparison = None
        if len(model_ids) > 1:
            try:
                version_comparison = self.analyzer.compare_versions(
                    model_ids, suite_name=suite_name
                )
            except Exception as e:
                logger.warning("failed_version_comparison", error=str(e))

        # Generate markdown report
        report_content = self._build_markdown_report(
            model_ids=model_ids,
            suite_name=suite_name,
            plots=plots,
            comparison_plot=comparison_plot,
            model_stats=model_stats,
            version_comparison=version_comparison,
        )

        # Write report
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info("report_generated", path=str(output_path))

        return output_path

    def _build_markdown_report(
        self,
        model_ids: list[str],
        suite_name: str | None,
        plots: list[tuple[str, Path]],
        comparison_plot: Path | None,
        model_stats: dict[str, dict[str, Any]],
        version_comparison: dict[str, Any] | None,
    ) -> str:
        """Build markdown report content."""
        lines = []

        # Header
        lines.append("# Learning Curve Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if suite_name:
            lines.append(f"**Benchmark Suite:** {suite_name}")
        lines.append(f"**Models Analyzed:** {len(model_ids)}")
        lines.append("")

        # Model comparison visualization
        if comparison_plot:
            lines.append("## Model Comparison")
            lines.append("")
            lines.append(f"![Model Comparison]({comparison_plot.name})")
            lines.append("")

        # Individual model sections
        for model_id in model_ids:
            lines.append(f"## {model_id}")
            lines.append("")

            # Learning curve plot
            model_plot = next((p for mid, p in plots if mid == model_id), None)
            if model_plot:
                lines.append(f"![Learning Curve - {model_id}]({model_plot.name})")
                lines.append("")

            # Statistics
            if model_id in model_stats:
                stats = model_stats[model_id]
                lines.append("### Statistics")
                lines.append("")
                lines.append(f"- **Data Points:** {stats['data_points']}")
                lines.append(f"- **Mean Accuracy:** {stats['mean_accuracy']:.2%}")
                lines.append(f"- **Standard Deviation:** {stats['std_dev']:.4f}")
                lines.append(f"- **Min Accuracy:** {stats['min_accuracy']:.2%}")
                lines.append(f"- **Max Accuracy:** {stats['max_accuracy']:.2%}")

                if "growth_rate" in stats:
                    lines.append(
                        f"- **Absolute Growth:** {stats['growth_rate']:+.2%}"
                    )
                    lines.append(
                        f"- **Relative Growth:** {stats['relative_growth']:+.2%}"
                    )

                lines.append("")

        # Version comparison table
        if version_comparison and "pairwise_differences" in version_comparison:
            lines.append("## Version Comparison")
            lines.append("")
            lines.append("| Model A | Model B | Accuracy Difference | Relative Improvement |")
            lines.append("|---------|---------|---------------------|---------------------|")

            for diff in version_comparison["pairwise_differences"]:
                lines.append(
                    f"| {diff['model_a']} | {diff['model_b']} | "
                    f"{diff['accuracy_difference']:+.2%} | "
                    f"{diff['relative_improvement']:+.2%} |"
                )

            lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")

        if model_stats:
            best_model = max(model_stats.items(), key=lambda x: x[1]["mean_accuracy"])
            lines.append(f"**Best Performing Model:** {best_model[0]} "
                        f"({best_model[1]['mean_accuracy']:.2%} mean accuracy)")

            if "growth_rate" in best_model[1]:
                lines.append(f"**Highest Growth:** {best_model[0]} "
                            f"({best_model[1]['growth_rate']:+.2%})")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*Report generated by LLM Algorithm Harness - Learning Curve Tracker*")

        return "\n".join(lines)
