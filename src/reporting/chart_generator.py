"""
Chart generation module using matplotlib.
"""

import io
import base64
from typing import Dict, List, Optional

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from src.models import ExecutionResult


class ChartGenerator:
    """Generate visualization charts using matplotlib."""

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
    def generate_success_rate_chart(metrics: Dict[str, Dict]) -> io.BytesIO:
        """
        Generate success rate comparison bar chart.

        Args:
            metrics: Dictionary mapping strategy name to metrics dict

        Returns:
            BytesIO containing PNG image
        """
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

    @staticmethod
    def generate_token_chart(
        metrics: Dict[str, Dict],
        results: Optional[Dict[str, List[ExecutionResult]]] = None
    ) -> io.BytesIO:
        """
        Generate token consumption line chart.

        Args:
            metrics: Dictionary mapping strategy name to metrics dict
            results: Optional dictionary mapping strategy name to results list (for percentile calculation)

        Returns:
            BytesIO containing PNG image
        """
        ChartGenerator._setup_chinese_font()

        strategies = list(metrics.keys())
        avg_tokens = [metrics[s].get('avg_tokens_per_problem', 0) for s in strategies]

        # Calculate percentiles if results are provided
        percentile_25 = []
        percentile_75 = []

        if results:
            for strategy in strategies:
                strategy_results = results.get(strategy, [])
                if strategy_results:
                    # Extract total tokens from each result
                    token_counts = []
                    for result in strategy_results:
                        total_tokens = sum(
                            iteration.prompt_tokens + iteration.completion_tokens
                            for iteration in result.iterations
                        )
                        token_counts.append(total_tokens)

                    # Calculate 25th and 75th percentiles
                    if token_counts:
                        p25 = np.percentile(token_counts, 25)
                        p75 = np.percentile(token_counts, 75)
                        percentile_25.append(p25)
                        percentile_75.append(p75)
                    else:
                        percentile_25.append(0)
                        percentile_75.append(0)
                else:
                    percentile_25.append(0)
                    percentile_75.append(0)

        fig, ax = plt.subplots(figsize=(10, 6))

        # Line plot with markers
        x_pos = range(len(strategies))
        ax.plot(x_pos, avg_tokens, marker='o', markersize=8, linewidth=2, color='#3498db', label='Average')

        # Add error bars if percentiles are available
        if percentile_25 and percentile_75:
            # Calculate error bar sizes (distance from mean to percentile)
            # Use max(0, ...) to ensure non-negative values
            yerr_lower = [max(0, avg - p25) for avg, p25 in zip(avg_tokens, percentile_25)]
            yerr_upper = [max(0, p75 - avg) for avg, p75 in zip(avg_tokens, percentile_75)]
            ax.errorbar(
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

        # Add value labels
        for i, (x, y) in enumerate(zip(x_pos, avg_tokens)):
            ax.text(x, y, f'{y:.0f}', ha='center', va='bottom', fontsize=9)

        ax.set_xlabel('Strategy', fontsize=12)
        ax.set_ylabel('Average Tokens', fontsize=12)
        ax.set_title('Token Consumption Comparison', fontsize=14, fontweight='bold')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(strategies, rotation=45, ha='right')
        ax.grid(axis='y', linestyle='--', alpha=0.3)
        ax.legend(loc='upper left')

        plt.tight_layout()

        return ChartGenerator._fig_to_bytes(fig)

    @staticmethod
    def generate_iteration_distribution(results: Dict[str, List[ExecutionResult]]) -> Optional[io.BytesIO]:
        """
        Generate iteration count distribution histogram.

        Args:
            results: Dictionary mapping strategy name to results list

        Returns:
            BytesIO containing PNG image, or None if all strategies are single-round
        """
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

        fig, ax = plt.subplots(figsize=(10, 6))

        # Prepare histogram data
        max_iterations = max(max(iters) for iters in iteration_data.values())
        bins = range(1, max_iterations + 2)

        # Plot histogram for each strategy
        for i, (strategy_name, iterations) in enumerate(iteration_data.items()):
            ax.hist(iterations, bins=bins, alpha=0.6, label=strategy_name, edgecolor='black')

        ax.set_xlabel('Iteration Count', fontsize=12)
        ax.set_ylabel('Number of Problems', fontsize=12)
        ax.set_title('Iteration Count Distribution', fontsize=14, fontweight='bold')
        ax.legend(loc='upper right')
        ax.grid(axis='y', linestyle='--', alpha=0.3)

        plt.tight_layout()

        return ChartGenerator._fig_to_bytes(fig)
