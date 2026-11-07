"""
Chart generation module using matplotlib.
"""

import base64
import io
import logging
import math
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from src.models import ExecutionResult

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generate visualization charts using matplotlib."""

    @staticmethod
    def _setup_chinese_font() -> None:
        """Setup Chinese font with fallback strategy."""
        fonts = ["SimHei", "Arial Unicode MS", "DejaVu Sans"]
        available_fonts = [f.name for f in fm.fontManager.ttflist]

        for font in fonts:
            if font in available_fonts:
                plt.rcParams["font.sans-serif"] = [font]
                break

        # Prevent minus sign display issue
        plt.rcParams["axes.unicode_minus"] = False

    @staticmethod
    def _fig_to_base64(fig: Any) -> str:
        """Convert matplotlib figure to base64 encoded string."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        buf.seek(0)
        base64_str = base64.b64encode(buf.read()).decode("utf-8")
        plt.close(fig)
        return base64_str

    @staticmethod
    def _fig_to_bytes(fig: Any) -> io.BytesIO:
        """Convert matplotlib figure to BytesIO."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        buf.seek(0)
        plt.close(fig)
        return buf

    @staticmethod
    def generate_success_rate_chart(
        metrics: dict[str, dict], title: str | None = None
    ) -> io.BytesIO | None:
        """
        Generate success rate comparison bar chart.

        Args:
            metrics: Dictionary mapping strategy name to metrics dict

        Returns:
            BytesIO containing PNG image, or None if generation fails
        """
        try:
            ChartGenerator._setup_chinese_font()

            strategies = list(metrics.keys())
            success_rates = [metrics[s].get("success_rate", 0) * 100 for s in strategies]

            fig, ax = plt.subplots(figsize=(10, 6))

            # Color coding: green (>=80%), yellow (50-80%), red (<50%)
            colors = []
            for rate in success_rates:
                if rate >= 80:
                    colors.append("#2ecc71")  # green
                elif rate >= 50:
                    colors.append("#f39c12")  # yellow
                else:
                    colors.append("#e74c3c")  # red

            bars = ax.bar(strategies, success_rates, color=colors, alpha=0.8, edgecolor="black")

            # Add value labels on top of bars
            for bar, rate in zip(bars, success_rates):
                height = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    height,
                    f"{rate:.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=10,
                    fontweight="bold",
                )

            ax.set_xlabel("Strategy", fontsize=12)
            ax.set_ylabel("Success Rate (%)", fontsize=12)
            ax.set_title(title or "Success Rate Comparison", fontsize=14, fontweight="bold")
            ax.set_ylim(0, 105)
            ax.grid(axis="y", linestyle="--", alpha=0.3)
            ax.legend(["≥80%", "50-80%", "<50%"], loc="upper right")

            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()

            return ChartGenerator._fig_to_bytes(fig)
        except Exception as e:
            logger.error(
                f"Failed to generate success rate chart: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            return None

    @staticmethod
    def _aggregate_trace_usage(
        results: list[ExecutionResult],
    ) -> tuple[list[int], list[float], int]:
        """
        Aggregate per-strategy token totals and known costs from llm_traces.

        Trace token totals already merge main and reflection rounds, and known
        costs are the merged ``pricing_metadata.total_cost`` values — the same
        semantics as ``harness._estimate_cost``, so charts and text reports
        reconcile. Results whose traces are missing entirely (unexecuted
        placeholders, budget-exhausted units) contribute their recorded token
        total and count as unknown cost; results with unknown-cost calls
        contribute only their known part and are flagged too.

        Returns:
            (token_counts, known_costs, unknown_units) per strategy, in order.
            ``known_costs`` entries are ``float("nan")`` when a strategy has no
            known cost data.
        """
        token_counts: list[int] = []
        known_costs: list[float] = []
        unknown_units = 0
        for result in results:
            traces = result.llm_traces or []
            trace_tokens = 0
            result_known_cost = 0.0
            result_unknown = False
            for trace in traces:
                trace_tokens += trace.get("total_tokens", 0)
                pricing = trace.get("pricing_metadata")
                if not isinstance(pricing, dict):
                    result_unknown = True
                    continue
                trace_cost = pricing.get("total_cost")
                if trace_cost is None or pricing.get("usage_known") is False:
                    result_unknown = True
                    continue
                result_known_cost += float(trace_cost)
            if not traces:
                # 无 trace 的结果：无法区分已计费与未执行，费用记为未知；
                # token 用结果记录的总额，如实计入用量轴。
                if result.total_tokens:
                    token_counts.append(result.total_tokens)
                unknown_units += 1
                known_costs.append(float("nan"))
                continue
            token_counts.append(trace_tokens)
            if result_unknown:
                unknown_units += 1
            # 已知部分照实入账；全部调用未知时没有已知美元值（NaN 不绘制）。
            if result_known_cost > 0 or not result_unknown:
                known_costs.append(result_known_cost)
            else:
                known_costs.append(float("nan"))
        return token_counts, known_costs, unknown_units

    @staticmethod
    def generate_token_chart(
        metrics: dict[str, dict],
        results: dict[str, list[ExecutionResult]] | None = None,
    ) -> io.BytesIO | None:
        """
        Generate token consumption line chart with historical known cost on dual Y-axis.

        Cost and usage come from each result's ``llm_traces`` (the same source as
        the text report): trace token totals already include reflection rounds,
        and the dollar axis only aggregates known ``pricing_metadata.total_cost``
        values. Calls with unknown cost are excluded from the dollar axis and
        annotated instead of being re-estimated (issue #368).

        Args:
            metrics: Dictionary mapping strategy name to metrics dict
            results: Optional dictionary mapping strategy name to results list (for percentile calculation)

        Returns:
            BytesIO containing PNG image, or None if generation fails
        """
        try:
            ChartGenerator._setup_chinese_font()

            strategies = list(metrics.keys())
            avg_tokens = [metrics[s].get("avg_tokens_per_problem", 0) for s in strategies]

            # Calculate percentiles if results are provided
            percentile_25: list[float] = []
            percentile_75: list[float] = []
            avg_costs: list[float] = []
            unknown_units_total = 0

            if results:
                for strategy in strategies:
                    strategy_results = results.get(strategy, [])
                    token_counts, known_costs, unknown_units = (
                        ChartGenerator._aggregate_trace_usage(strategy_results)
                    )
                    unknown_units_total += unknown_units
                    known_values = [c for c in known_costs if not math.isnan(c)]
                    avg_cost = float(np.mean(known_values)) if known_values else float("nan")
                    avg_costs.append(avg_cost)

                    # Calculate 25th and 75th percentiles
                    if token_counts:
                        p25 = np.percentile(token_counts, 25)
                        p75 = np.percentile(token_counts, 75)
                        percentile_25.append(float(p25))
                        percentile_75.append(float(p75))
                    else:
                        percentile_25.append(0.0)
                        percentile_75.append(0.0)

            # 无已知费用的策略不绘制伪造美元值（issue #368）；成本轴只画历史已知部分。
            plot_cost = any(not math.isnan(c) for c in avg_costs)

            # Create figure and axes
            fig, ax1 = plt.subplots(figsize=(12, 6))

            # Primary Y-axis: Tokens (left)
            x_pos = range(len(strategies))
            color_tokens = "#3498db"
            ax1.plot(
                x_pos,
                avg_tokens,
                marker="o",
                markersize=8,
                linewidth=2,
                color=color_tokens,
                label="Average Tokens",
            )

            # Add error bars if percentiles are available
            if percentile_25 and percentile_75:
                # Validate percentiles and recalculate avg from results if inconsistent
                yerr_lower: list[float] = []
                yerr_upper: list[float] = []

                pairs = [
                    (float(avg), float(p25), float(p75))
                    for avg, p25, p75 in zip(avg_tokens, percentile_25, percentile_75)
                ]
                for i, (avg_float, p25_float, p75_float) in enumerate(pairs):
                    # Check for data consistency: p25 should be <= avg <= p75
                    # If not, it means metrics and results are from different datasets
                    if p25_float > 0 and p75_float > 0:
                        # If percentiles seem valid but don't bracket avg, log warning
                        if p25_float <= avg_float <= p75_float:
                            yerr_lower.append(avg_float - p25_float)
                            yerr_upper.append(p75_float - avg_float)
                        else:
                            # Inconsistent data - log warning and skip error bars for this strategy
                            strategy_name = (
                                strategies[i] if i < len(strategies) else f"strategy_{i}"
                            )
                            logger.warning(
                                f"Token chart: percentiles don't bracket average for {strategy_name} "
                                f"(p25={p25_float:.0f}, avg={avg_float:.0f}, p75={p75_float:.0f}). "
                                f"This suggests metrics and results are from different datasets. Skipping error bars."
                            )
                            yerr_lower.append(0.0)
                            yerr_upper.append(0.0)
                    else:
                        # No percentile data for this strategy
                        yerr_lower.append(0)
                        yerr_upper.append(0)

                # Only show error bars if at least one strategy has valid data
                if any(y > 0 for y in yerr_lower + yerr_upper):
                    ax1.errorbar(
                        x_pos,
                        avg_tokens,
                        yerr=[yerr_lower, yerr_upper],
                        fmt="none",
                        ecolor="#95a5a6",
                        elinewidth=2,
                        capsize=5,
                        capthick=2,
                        alpha=0.7,
                        label="25th-75th percentile",
                    )

            ax1.set_xlabel("Strategy", fontsize=12)
            ax1.set_ylabel("Average Tokens", fontsize=12, color=color_tokens)
            ax1.tick_params(axis="y", labelcolor=color_tokens)
            ax1.set_xticks(x_pos)
            ax1.set_xticklabels(strategies, rotation=45, ha="right")
            ax1.grid(axis="y", linestyle="--", alpha=0.3)

            # Secondary Y-axis: Known historical cost (right)
            ax2 = ax1.twinx()
            color_cost = "#2ecc71"
            if plot_cost:
                ax2.plot(
                    x_pos,
                    avg_costs,
                    marker="s",
                    markersize=7,
                    linewidth=2,
                    linestyle="--",
                    color=color_cost,
                    label="Known Cost",
                )

            ax2.set_ylabel("Known Cost (USD)", fontsize=12, color=color_cost)
            ax2.tick_params(axis="y", labelcolor=color_cost)

            # Add value labels for tokens and known costs
            for i, (x, tokens) in enumerate(zip(x_pos, avg_tokens)):
                # Token label
                ax1.text(
                    x,
                    tokens,
                    f"{tokens:.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    color=color_tokens,
                )

            if plot_cost:
                # Cost labels with smart formatting (only known values; NaN strategies skipped)
                for i, (x, cost) in enumerate(zip(x_pos, avg_costs)):
                    if cost is None or math.isnan(cost):
                        continue
                    if cost < 1.0:
                        cost_str = f"${cost:.4f}"
                    else:
                        cost_str = f"${cost:.2f}"
                    ax2.text(x, cost, cost_str, ha="center", va="top", fontsize=9, color=color_cost)

            # Combined legend
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

            # Honest title: costs are historical known values, never estimated
            title = "Token Consumption and Known Cost Comparison"
            if unknown_units_total:
                title += f" ({unknown_units_total} result unit(s) with unknown cost excluded)"
            elif not plot_cost:
                title += " (no known cost data)"
            plt.title(title, fontsize=14, fontweight="bold")
            plt.tight_layout()

            return ChartGenerator._fig_to_bytes(fig)
        except Exception as e:
            logger.error(
                f"Failed to generate token chart: {type(e).__name__}: {str(e)}", exc_info=True
            )
            return None

    @staticmethod
    def generate_iteration_distribution(
        results: dict[str, list[ExecutionResult]],
    ) -> io.BytesIO | None:
        """
        Generate iteration count distribution as grouped bar chart.

        Args:
            results: Dictionary mapping strategy name to results list

        Returns:
            BytesIO containing PNG image, or None if all strategies are single-round or generation fails
        """
        try:
            ChartGenerator._setup_chinese_font()

            # Collect iteration counts
            iteration_data = {}
            has_multi_round = False

            for strategy_name, strategy_results in results.items():
                iterations = [len(r.iterations) for r in strategy_results]
                if any(it > 1 for it in iterations):
                    has_multi_round = True
                    iteration_data[strategy_name] = iterations

            # Return None if no multi-round strategies
            if not has_multi_round:
                return None

            fig, ax = plt.subplots(figsize=(12, 6))

            # Count occurrences of each iteration number for each strategy
            max_iterations = max(max(iters) for iters in iteration_data.values())
            iteration_categories = list(range(1, max_iterations + 1))

            # Prepare data for grouped bar chart
            strategy_names = list(iteration_data.keys())
            num_strategies = len(strategy_names)

            # Count frequency for each iteration number per strategy
            frequency_data: dict[str, list[int]] = {}
            for strategy_name in strategy_names:
                iterations = iteration_data[strategy_name]
                frequency_data[strategy_name] = []
                for iter_num in iteration_categories:
                    count = iterations.count(iter_num)
                    frequency_data[strategy_name].append(count)

            # Set up bar positions
            bar_width = 0.8 / num_strategies  # Total width of 0.8 divided by number of strategies
            x_positions = np.arange(len(iteration_categories))

            # Color palette
            colors = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"]

            # Plot grouped bars
            for i, strategy_name in enumerate(strategy_names):
                offset = (i - num_strategies / 2 + 0.5) * bar_width
                bars = ax.bar(
                    x_positions + offset,
                    frequency_data[strategy_name],
                    bar_width,
                    label=strategy_name,
                    color=colors[i % len(colors)],
                    alpha=0.8,
                    edgecolor="black",
                    linewidth=0.5,
                )

                # Add value labels on bars (only if count > 0)
                for j, (bar, count) in enumerate(zip(bars, frequency_data[strategy_name])):
                    if count > 0:
                        height = bar.get_height()
                        ax.text(
                            bar.get_x() + bar.get_width() / 2.0,
                            height,
                            f"{int(count)}",
                            ha="center",
                            va="bottom",
                            fontsize=8,
                            fontweight="bold",
                        )

            ax.set_xlabel("Iteration Count", fontsize=12)
            ax.set_ylabel("Number of Problems", fontsize=12)
            ax.set_title("Iteration Count Distribution", fontsize=14, fontweight="bold")
            ax.set_xticks(x_positions)
            ax.set_xticklabels([str(i) for i in iteration_categories])
            ax.legend(loc="upper right")
            ax.grid(axis="y", linestyle="--", alpha=0.3)

            # Set y-axis to start at 0
            ax.set_ylim(bottom=0)

            plt.tight_layout()

            return ChartGenerator._fig_to_bytes(fig)
        except Exception as e:
            logger.error(
                f"Failed to generate iteration distribution: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            return None

    @staticmethod
    def generate_capability_radar(
        dimension_scores: dict[str, dict[str, float]],
        model_names: list[str],
        dimension_names: list[str],
    ) -> str:
        """
        Generate a radar chart showing model capabilities across dimensions.

        Args:
            dimension_scores: Nested dict {model_name: {dimension: score_0_to_100}}
            model_names: List of model names to include
            dimension_names: List of dimension names (e.g., ["Array", "Graph", ...])

        Returns:
            Base64-encoded PNG image string
        """
        import numpy as np

        # Number of dimensions
        num_dimensions = len(dimension_names)
        if num_dimensions == 0:
            return ""

        # Configure Chinese font support
        plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        # Create angles for each dimension
        angles = np.linspace(0, 2 * np.pi, num_dimensions, endpoint=False).tolist()
        # Close the plot by appending the first angle
        angles += angles[:1]

        # Create polar plot with 8x8 inches size
        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection="polar"))

        # Plot each model
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]  # blue, orange, green, red
        for idx, model_name in enumerate(model_names):
            if model_name not in dimension_scores:
                continue

            # Get scores for this model
            scores = [dimension_scores[model_name].get(dim, 0.0) for dim in dimension_names]
            # Close the plot by appending the first score
            scores += scores[:1]

            color = colors[idx % len(colors)]
            ax.plot(angles, scores, "o-", linewidth=2, label=model_name, color=color)
            ax.fill(angles, scores, alpha=0.3, color=color)

        # Set dimension labels with rotation
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(dimension_names, size=10)

        # Set radial limits (0-100 scale)
        ax.set_ylim(0, 100)
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.set_yticklabels(["0", "20", "40", "60", "80", "100"], size=9)

        # Enhance grid appearance
        ax.grid(True, linestyle="--", alpha=0.7)

        # Add legend if multiple models
        if len(model_names) > 1:
            ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)

        plt.tight_layout()

        return ChartGenerator._fig_to_base64(fig)
