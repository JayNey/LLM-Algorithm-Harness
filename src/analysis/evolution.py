"""
Code evolution analysis for multi-round iteration strategies.

This module analyzes code quality trends across iterations and identifies
quality degradation points.
"""

from pathlib import Path

from src.models import ExecutionResult


class QualityDrop:
    """Represents a quality drop at a specific iteration."""

    def __init__(
        self,
        iteration: int,
        metric_name: str,
        previous_value: float,
        current_value: float,
        reason: str,
    ):
        self.iteration = iteration
        self.metric_name = metric_name
        self.previous_value = previous_value
        self.current_value = current_value
        self.reason = reason


class EvolutionAnalyzer:
    """Analyzes code quality evolution across multi-round iterations."""

    def __init__(self, execution_result: ExecutionResult):
        """
        Initialize the analyzer with an execution result.

        Args:
            execution_result: Result from a multi-round strategy execution
        """
        self.execution_result = execution_result
        self.iterations = execution_result.iterations or []

    def identify_quality_drops(self) -> list[QualityDrop]:
        """
        Identify iterations where code quality dropped compared to previous iteration.

        Uses combined thresholds:
        - Single metric: >15% relative decrease from previous iteration
        - Overall score: >10 points absolute decrease (out of 100)
        - First iteration is not evaluated (no baseline)

        Returns:
            List of QualityDrop objects representing quality degradation points
        """
        drops = []

        for i in range(1, len(self.iterations)):
            prev_iter = self.iterations[i - 1]
            curr_iter = self.iterations[i]

            # Skip if either iteration lacks quality data
            if not prev_iter.code_quality or not curr_iter.code_quality:
                continue

            prev_q = prev_iter.code_quality
            curr_q = curr_iter.code_quality

            # Check overall score drop (absolute threshold: 10 points)
            if prev_q.overall_score is not None and curr_q.overall_score is not None:
                score_drop = prev_q.overall_score - curr_q.overall_score
                if score_drop >= 10.0:
                    drops.append(
                        QualityDrop(
                            iteration=curr_iter.iteration,
                            metric_name="overall_score",
                            previous_value=prev_q.overall_score,
                            current_value=curr_q.overall_score,
                            reason="",  # Will be filled by analyze_drop_reason
                        )
                    )

            # Check individual metric drops (relative threshold: 15%)
            # Extract actual scores from nested objects
            metrics = []

            if prev_q.time_complexity and curr_q.time_complexity:
                prev_val = prev_q.time_complexity.performance_score
                curr_val = curr_q.time_complexity.performance_score
                if prev_val is not None and curr_val is not None:
                    metrics.append(("time_complexity", prev_val, curr_val))

            if prev_q.space_complexity and curr_q.space_complexity:
                prev_val = prev_q.space_complexity.memory_efficiency_score
                curr_val = curr_q.space_complexity.memory_efficiency_score
                if prev_val is not None and curr_val is not None:
                    metrics.append(("space_complexity", prev_val, curr_val))

            if prev_q.readability and curr_q.readability:
                prev_val = prev_q.readability.readability_score
                curr_val = curr_q.readability.readability_score
                if prev_val is not None and curr_val is not None:
                    metrics.append(("readability", prev_val, curr_val))

            if prev_q.style_consistency and curr_q.style_consistency:
                prev_val = prev_q.style_consistency.style_score
                curr_val = curr_q.style_consistency.style_score
                if prev_val is not None and curr_val is not None:
                    metrics.append(("style_consistency", prev_val, curr_val))

            for metric_name, prev_val, curr_val in metrics:
                if prev_val > 0:
                    relative_drop = (prev_val - curr_val) / prev_val
                    if relative_drop >= 0.15:  # 15% threshold
                        drops.append(
                            QualityDrop(
                                iteration=curr_iter.iteration,
                                metric_name=metric_name,
                                previous_value=prev_val,
                                current_value=curr_val,
                                reason="",
                            )
                        )

        return drops

    def analyze_drop_reason(self, drop: QualityDrop) -> str:
        """
        Analyze the reason for a quality drop using rule-based heuristics.

        Args:
            drop: QualityDrop object to analyze

        Returns:
            Human-readable explanation of the drop reason
        """
        # Find the iteration that contains this drop
        iteration = None
        prev_iteration = None
        for i, iter_result in enumerate(self.iterations):
            if iter_result.iteration == drop.iteration:
                iteration = iter_result
                if i > 0:
                    prev_iteration = self.iterations[i - 1]
                break

        if not iteration or not prev_iteration:
            return "Unable to analyze: iteration data not found"

        # Check for sandbox failures
        if iteration.sandbox_result and iteration.sandbox_result.status != "success":
            status = iteration.sandbox_result.status
            if status == "syntax_error":
                return "Introduced syntax error"
            elif status == "runtime_error":
                return "Introduced runtime error"
            elif status == "timeout":
                return "Code timeout - possible infinite loop or excessive complexity"
            elif status == "failed":
                return "Test failures introduced"
            else:
                return f"Code execution failed: {status}"

        # Rule-based pattern detection
        curr_q = iteration.code_quality
        prev_q = prev_iteration.code_quality

        if not curr_q or not prev_q:
            return "Quality data incomplete"

        # Pattern 1: Complexity increased but tests improved
        if drop.metric_name in ["time_complexity", "space_complexity"]:
            prev_sandbox = prev_iteration.sandbox_result
            curr_sandbox = iteration.sandbox_result
            if prev_sandbox and curr_sandbox:
                # Calculate pass rates from test_results
                prev_total = len(prev_sandbox.test_results)
                prev_passed = sum(1 for t in prev_sandbox.test_results if t.passed)
                prev_pass_rate = prev_passed / prev_total if prev_total > 0 else 0

                curr_total = len(curr_sandbox.test_results)
                curr_passed = sum(1 for t in curr_sandbox.test_results if t.passed)
                curr_pass_rate = curr_passed / curr_total if curr_total > 0 else 0

                if curr_pass_rate > prev_pass_rate:
                    return "Over-optimization: complexity increased to fix failing tests"

        # Pattern 2: Code bloat (readability dropped)
        if drop.metric_name == "readability":
            if curr_q.readability and prev_q.readability:
                curr_complexity = curr_q.readability.cyclomatic_complexity
                prev_complexity = prev_q.readability.cyclomatic_complexity
                if (
                    curr_complexity
                    and prev_complexity
                    and curr_complexity > prev_complexity * 1.2
                ):
                    return "Code bloat: significant complexity increase detected"

        # Pattern 3: Style degradation
        if drop.metric_name == "style_consistency":
            if curr_q.style_consistency and prev_q.style_consistency:
                violations_increase = (
                    curr_q.style_consistency.style_violations
                    - prev_q.style_consistency.style_violations
                )
                if violations_increase > 5:
                    return f"Style degradation: {violations_increase} new style violations"

        # Pattern 4: Multiple metrics dropped simultaneously
        if drop.metric_name == "overall_score":
            dropped_metrics = []
            if prev_q.readability and curr_q.readability:
                if (
                    prev_q.readability.readability_score
                    and curr_q.readability.readability_score
                ):
                    if curr_q.readability.readability_score < prev_q.readability.readability_score:
                        dropped_metrics.append("readability")

            if prev_q.style_consistency and curr_q.style_consistency:
                if prev_q.style_consistency.style_score and curr_q.style_consistency.style_score:
                    if curr_q.style_consistency.style_score < prev_q.style_consistency.style_score:
                        dropped_metrics.append("style")

            if len(dropped_metrics) >= 2:
                return f"Comprehensive quality decline across {', '.join(dropped_metrics)}"

        # Default explanation
        percent_drop = (
            (drop.previous_value - drop.current_value) / drop.previous_value * 100
            if drop.previous_value > 0
            else 0
        )
        return (
            f"{drop.metric_name.replace('_', ' ').title()} decreased by "
            f"{percent_drop:.1f}% (from {drop.previous_value:.1f} to {drop.current_value:.1f})"
        )


    def generate_evolution_chart(self, output_path: Path) -> None:
        """
        Generate a visualization of quality metrics evolution over iterations.

        Args:
            output_path: Path where the PNG chart will be saved
        """
        import matplotlib.pyplot as plt

        # Collect data points
        iterations = []
        overall_scores: list[float | None] = []
        time_scores: list[float | None] = []
        space_scores: list[float | None] = []
        readability_scores: list[float | None] = []
        style_scores: list[float | None] = []

        for iter_result in self.iterations:
            if not iter_result.code_quality:
                continue

            iterations.append(iter_result.iteration)
            q = iter_result.code_quality

            overall_scores.append(q.overall_score if q.overall_score is not None else None)

            if q.time_complexity and q.time_complexity.performance_score is not None:
                time_scores.append(q.time_complexity.performance_score)
            else:
                time_scores.append(None)

            if q.space_complexity and q.space_complexity.memory_efficiency_score is not None:
                space_scores.append(q.space_complexity.memory_efficiency_score)
            else:
                space_scores.append(None)

            if q.readability and q.readability.readability_score is not None:
                readability_scores.append(q.readability.readability_score)
            else:
                readability_scores.append(None)

            if q.style_consistency and q.style_consistency.style_score is not None:
                style_scores.append(q.style_consistency.style_score)
            else:
                style_scores.append(None)

        if len(iterations) < 2:
            raise ValueError("Need at least 2 iterations with quality data to generate chart")

        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

        # Top plot: Overall score
        ax1.plot(iterations, overall_scores, marker="o", linewidth=2, label="Overall Score")
        ax1.set_xlabel("Iteration")
        ax1.set_ylabel("Score (0-100)")
        ax1.set_title("Code Quality Evolution - Overall Score")
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(0, 100)
        ax1.legend()

        # Bottom plot: Individual metrics
        if any(s is not None for s in time_scores):
            ax2.plot(iterations, time_scores, marker="s", label="Time Complexity", alpha=0.7)
        if any(s is not None for s in space_scores):
            ax2.plot(iterations, space_scores, marker="^", label="Space Complexity", alpha=0.7)
        if any(s is not None for s in readability_scores):
            ax2.plot(iterations, readability_scores, marker="D", label="Readability", alpha=0.7)
        if any(s is not None for s in style_scores):
            ax2.plot(iterations, style_scores, marker="v", label="Style Consistency", alpha=0.7)

        ax2.set_xlabel("Iteration")
        ax2.set_ylabel("Score (0-100)")
        ax2.set_title("Code Quality Evolution - Individual Metrics")
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, 100)
        ax2.legend()

        plt.tight_layout()

        # Save figure
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()


    def generate_evolution_report(self) -> str:
        """
        Generate a text report summarizing quality evolution and drops.

        Returns:
            Markdown-formatted report text
        """
        lines = []
        lines.append("## Code Quality Evolution Analysis\n")

        # Summary statistics
        lines.append("### Summary\n")
        lines.append(f"- Total iterations: {len(self.iterations)}")

        iterations_with_quality = sum(
            1 for iter_result in self.iterations if iter_result.code_quality is not None
        )
        lines.append(f"- Iterations with quality data: {iterations_with_quality}")

        # Overall score trend
        overall_scores = []
        for iter_result in self.iterations:
            if iter_result.code_quality and iter_result.code_quality.overall_score is not None:
                overall_scores.append(iter_result.code_quality.overall_score)

        if overall_scores:
            initial_score = overall_scores[0]
            final_score = overall_scores[-1]
            score_change = final_score - initial_score
            lines.append(f"- Initial overall score: {initial_score:.1f}")
            lines.append(f"- Final overall score: {final_score:.1f}")
            lines.append(
                f"- Net change: {score_change:+.1f} "
                f"({'improvement' if score_change > 0 else 'decline' if score_change < 0 else 'no change'})"
            )

        # Quality drops
        lines.append("\n### Quality Drops Detected\n")
        drops = self.identify_quality_drops()

        if not drops:
            lines.append("No significant quality drops detected.\n")
        else:
            lines.append(f"Found {len(drops)} quality drop(s):\n")

            # Group drops by iteration
            drops_by_iteration: dict[int, list[QualityDrop]] = {}
            for drop in drops:
                if drop.iteration not in drops_by_iteration:
                    drops_by_iteration[drop.iteration] = []
                drops_by_iteration[drop.iteration].append(drop)

            for iteration in sorted(drops_by_iteration.keys()):
                lines.append(f"\n**Iteration {iteration}:**\n")
                for drop in drops_by_iteration[iteration]:
                    reason = self.analyze_drop_reason(drop)
                    metric_display = drop.metric_name.replace("_", " ").title()
                    lines.append(
                        f"- {metric_display}: {drop.previous_value:.1f} → {drop.current_value:.1f}"
                    )
                    lines.append(f"  - Reason: {reason}")

        # Iteration-by-iteration details
        lines.append("\n### Iteration Details\n")
        for iter_result in self.iterations:
            lines.append(f"\n**Iteration {iter_result.iteration}:**\n")

            if not iter_result.code_quality:
                lines.append("- No quality data available")
                continue

            q = iter_result.code_quality

            if q.overall_score is not None:
                lines.append(f"- Overall Score: {q.overall_score:.1f}")

            if q.time_complexity and q.time_complexity.performance_score is not None:
                lines.append(f"- Time Complexity: {q.time_complexity.performance_score:.1f}")

            if q.space_complexity and q.space_complexity.memory_efficiency_score is not None:
                lines.append(
                    f"- Space Complexity: {q.space_complexity.memory_efficiency_score:.1f}"
                )

            if q.readability and q.readability.readability_score is not None:
                lines.append(f"- Readability: {q.readability.readability_score:.1f}")

            if q.style_consistency and q.style_consistency.style_score is not None:
                lines.append(f"- Style Consistency: {q.style_consistency.style_score:.1f}")

        return "\n".join(lines)

