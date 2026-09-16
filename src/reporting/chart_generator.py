"""
Chart generation module using matplotlib.
"""

import io
import base64
import logging
from typing import Dict, List, Optional

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from src.models import ExecutionResult

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generate visualization charts using matplotlib."""

    # Pricing per 1M tokens (USD) - Based on 2026-09 official pricing
    # Format: (input_price, output_price)
    MODEL_PRICING = {
        'gpt-4': (30.0, 60.0),
        'gpt-4-turbo': (10.0, 30.0),
        'gpt-3.5-turbo': (0.5, 1.5),
        'claude-3-opus': (15.0, 75.0),
        'claude-3-sonnet': (3.0, 15.0),
        'claude-3-5-sonnet': (3.0, 15.0),
        'claude-3-haiku': (0.25, 1.25),
        'gemini-1.5-pro': (1.25, 5.0),  # Fixed: was (3.5, 10.5)
        'gemini-1.5-flash': (0.35, 1.05),
        'default': (10.0, 30.0),  # Fixed: was (1.0, 3.0) - Conservative default for unknown models
    }

    @staticmethod
    def _calculate_cost(
        prompt_tokens: int,
        completion_tokens: int,
        model: Optional[str] = None
    ) -> float:
        """
        Calculate cost based on token usage and model pricing.

        Args:
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            model: Model name (e.g., 'gpt-4', 'claude-3-sonnet')

        Returns:
            Estimated cost in USD
        """
        # Normalize model name to lowercase for matching
        model_key = model.lower() if model else 'default'

        # Try exact match first
        if model_key in ChartGenerator.MODEL_PRICING:
            input_price, output_price = ChartGenerator.MODEL_PRICING[model_key]
        else:
            # Try partial match (e.g., 'gpt-4-0125-preview' matches 'gpt-4')
            matched = False
            for key in ChartGenerator.MODEL_PRICING:
                if key != 'default' and key in model_key:
                    input_price, output_price = ChartGenerator.MODEL_PRICING[key]
                    matched = True
                    break

            if not matched:
                # Use default pricing
                input_price, output_price = ChartGenerator.MODEL_PRICING['default']

        # Calculate cost (prices are per 1M tokens)
        cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
        return cost

    @staticmethod
    def _setup_chinese_font():
        """Setup Chinese font with fallback strategy."""
        fonts = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
        available_fonts = [f.name for f in fm.fontManager.ttflist]

        for font in fonts:
            if font in available_fonts:
                plt.rcParams['font.sans-serif'] = [font]
                break

        # Prevent minus sign display issue
        plt.rcParams['axes.unicode_minus'] = False

    @staticmethod
    def _fig_to_base64(fig) -> str:
        """Convert matplotlib figure to base64 encoded string."""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        base64_str = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
        return base64_str

    @staticmethod
    def _fig_to_bytes(fig) -> io.BytesIO:
        """Convert matplotlib figure to BytesIO."""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf

    @staticmethod
    def generate_success_rate_chart(metrics: Dict[str, Dict]) -> Optional[io.BytesIO]:
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
            success_rates = [metrics[s].get('success_rate', 0) * 100 for s in strategies]

            fig, ax = plt.subplots(figsize=(10, 6))

            # Color coding: green (>=80%), yellow (50-80%), red (<50%)
            colors = []
            for rate in success_rates:
                if rate >= 80:
                    colors.append('#2ecc71')  # green
                elif rate >= 50:
                    colors.append('#f39c12')  # yellow
                else:
                    colors.append('#e74c3c')  # red

            bars = ax.bar(strategies, success_rates, color=colors, alpha=0.8, edgecolor='black')

            # Add value labels on top of bars
            for bar, rate in zip(bars, success_rates):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2., height,
                       f'{rate:.1f}%',
                       ha='center', va='bottom', fontsize=10, fontweight='bold')

            ax.set_xlabel('Strategy', fontsize=12)
            ax.set_ylabel('Success Rate (%)', fontsize=12)
            ax.set_title('Success Rate Comparison', fontsize=14, fontweight='bold')
            ax.set_ylim(0, 105)
            ax.grid(axis='y', linestyle='--', alpha=0.3)
            ax.legend(['≥80%', '50-80%', '<50%'], loc='upper right')

            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()

            return ChartGenerator._fig_to_bytes(fig)
        except Exception as e:
            logger.error(f"Failed to generate success rate chart: {type(e).__name__}: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def generate_token_chart(
        metrics: Dict[str, Dict],
        results: Optional[Dict[str, List[ExecutionResult]]] = None,
        model: Optional[str] = None
    ) -> Optional[io.BytesIO]:
        """
        Generate token consumption line chart with cost estimation on dual Y-axis.

        Args:
            metrics: Dictionary mapping strategy name to metrics dict
            results: Optional dictionary mapping strategy name to results list (for percentile calculation)
            model: Optional model name for cost calculation

        Returns:
            BytesIO containing PNG image, or None if generation fails
        """
        try:
            ChartGenerator._setup_chinese_font()

            strategies = list(metrics.keys())
            avg_tokens = [metrics[s].get('avg_tokens_per_problem', 0) for s in strategies]

            # Calculate percentiles if results are provided
            percentile_25 = []
            percentile_75 = []
            avg_costs = []

            if results:
                for strategy in strategies:
                strategy_results = results.get(strategy, [])
                if strategy_results:
                    # Extract total tokens from each result
                    token_counts = []
                    costs = []

                    for result in strategy_results:
                        total_prompt = 0
                        total_completion = 0
                        result_cost = 0.0

                        for iteration in result.iterations:
                            total_prompt += iteration.prompt_tokens
                            total_completion += iteration.completion_tokens
                            # Calculate cost per iteration to preserve input/output pricing
                            result_cost += ChartGenerator._calculate_cost(
                                iteration.prompt_tokens,
                                iteration.completion_tokens,
                                model
                            )

                        total_tokens = total_prompt + total_completion
                        token_counts.append(total_tokens)
                        costs.append(result_cost)

                    # Calculate 25th and 75th percentiles
                    if token_counts:
                        p25 = np.percentile(token_counts, 25)
                        p75 = np.percentile(token_counts, 75)
                        percentile_25.append(p25)
                        percentile_75.append(p75)

                        # Calculate average cost
                        avg_cost = np.mean(costs) if costs else 0
                        avg_costs.append(avg_cost)
                    else:
                        percentile_25.append(0)
                        percentile_75.append(0)
                        avg_costs.append(0)
                else:
                    percentile_25.append(0)
                    percentile_75.append(0)
                    avg_costs.append(0)

            # If no results provided, estimate cost using 70/30 split
            use_estimated_split = False
            if not avg_costs or all(c == 0 for c in avg_costs):
                use_estimated_split = True
                avg_costs = []
                for avg_token in avg_tokens:
                    # Assume 70% input, 30% output tokens
                    estimated_prompt = int(avg_token * 0.7)
                    estimated_completion = int(avg_token * 0.3)
                    cost = ChartGenerator._calculate_cost(estimated_prompt, estimated_completion, model)
                    avg_costs.append(cost)

                fig, ax1 = plt.subplots(figsize=(12, 6))

            # Primary Y-axis: Tokens (left)
            x_pos = range(len(strategies))
            color_tokens = '#3498db'
            ax1.plot(x_pos, avg_tokens, marker='o', markersize=8, linewidth=2,
                    color=color_tokens, label='Average Tokens')

            # Add error bars if percentiles are available
            if percentile_25 and percentile_75:
                # Validate percentiles and recalculate avg from results if inconsistent
                yerr_lower = []
                yerr_upper = []

                for i, (avg, p25, p75) in enumerate(zip(avg_tokens, percentile_25, percentile_75)):
                    # Check for data consistency: p25 should be <= avg <= p75
                    # If not, it means metrics and results are from different datasets
                    if p25 > 0 and p75 > 0:
                        # If percentiles seem valid but don't bracket avg, log warning
                        if p25 <= avg <= p75:
                            yerr_lower.append(avg - p25)
                            yerr_upper.append(p75 - avg)
                        else:
                            # Inconsistent data - log warning and skip error bars for this strategy
                            strategy_name = strategies[i] if i < len(strategies) else f"strategy_{i}"
                            logger.warning(
                                f"Token chart: percentiles don't bracket average for {strategy_name} "
                                f"(p25={p25:.0f}, avg={avg:.0f}, p75={p75:.0f}). "
                                f"This suggests metrics and results are from different datasets. Skipping error bars."
                            )
                            yerr_lower.append(0)
                            yerr_upper.append(0)
                    else:
                        # No percentile data for this strategy
                        yerr_lower.append(0)
                        yerr_upper.append(0)

                # Only show error bars if at least one strategy has valid data
                if any(y > 0 for y in yerr_lower + yerr_upper):
                    ax1.errorbar(
                        x_pos, avg_tokens,
                        yerr=[yerr_lower, yerr_upper],
                        fmt='none',
                        ecolor='#95a5a6',
                        elinewidth=2,
                        capsize=5,
                        capthick=2,
                        alpha=0.7,
                        label='25th-75th percentile'
                    )

            ax1.set_xlabel('Strategy', fontsize=12)
            ax1.set_ylabel('Average Tokens', fontsize=12, color=color_tokens)
            ax1.tick_params(axis='y', labelcolor=color_tokens)
            ax1.set_xticks(x_pos)
            ax1.set_xticklabels(strategies, rotation=45, ha='right')
            ax1.grid(axis='y', linestyle='--', alpha=0.3)

            # Secondary Y-axis: Cost (right)
            ax2 = ax1.twinx()
            color_cost = '#2ecc71'
            ax2.plot(x_pos, avg_costs, marker='s', markersize=7, linewidth=2,
                    linestyle='--', color=color_cost, label='Estimated Cost')

            ax2.set_ylabel('Estimated Cost (USD)', fontsize=12, color=color_cost)
            ax2.tick_params(axis='y', labelcolor=color_cost)

            # Add value labels for tokens and costs
            for i, (x, tokens, cost) in enumerate(zip(x_pos, avg_tokens, avg_costs)):
                # Token label
                ax1.text(x, tokens, f'{tokens:.0f}', ha='center', va='bottom',
                        fontsize=9, color=color_tokens)

                # Cost label with smart formatting
                if cost < 1.0:
                    cost_str = f'${cost:.4f}'
                else:
                    cost_str = f'${cost:.2f}'
                ax2.text(x, cost, cost_str, ha='center', va='top',
                        fontsize=9, color=color_cost)

            # Combined legend
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

            # Add title with estimation note if 70/30 split was used
            title = 'Token Consumption and Cost Comparison'
            if use_estimated_split:
                title += ' (cost estimated using 70/30 input/output ratio)'
            else:
                title += ' (estimated)'
            plt.title(title, fontsize=14, fontweight='bold')
            plt.tight_layout()

            return ChartGenerator._fig_to_bytes(fig)
        except Exception as e:
            logger.error(f"Failed to generate token chart: {type(e).__name__}: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def generate_iteration_distribution(results: Dict[str, List[ExecutionResult]]) -> Optional[io.BytesIO]:
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
            frequency_data = {}
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
            colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c']

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
                    edgecolor='black',
                    linewidth=0.5
                )

                # Add value labels on bars (only if count > 0)
                for j, (bar, count) in enumerate(zip(bars, frequency_data[strategy_name])):
                    if count > 0:
                        height = bar.get_height()
                        ax.text(
                            bar.get_x() + bar.get_width() / 2.,
                            height,
                            f'{int(count)}',
                            ha='center',
                            va='bottom',
                            fontsize=8,
                            fontweight='bold'
                        )

            ax.set_xlabel('Iteration Count', fontsize=12)
            ax.set_ylabel('Number of Problems', fontsize=12)
            ax.set_title('Iteration Count Distribution', fontsize=14, fontweight='bold')
            ax.set_xticks(x_positions)
            ax.set_xticklabels(iteration_categories)
            ax.legend(loc='upper right')
            ax.grid(axis='y', linestyle='--', alpha=0.3)

            # Set y-axis to start at 0
            ax.set_ylim(bottom=0)

            plt.tight_layout()

            return ChartGenerator._fig_to_bytes(fig)
        except Exception as e:
            logger.error(f"Failed to generate iteration distribution: {type(e).__name__}: {str(e)}", exc_info=True)
            return None
