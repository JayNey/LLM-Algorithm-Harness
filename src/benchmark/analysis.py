"""Trend analysis and visualization for learning curves."""

from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from src.benchmark.history import BenchmarkHistoryStorage
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TrendAnalyzer:
    """
    Analyze and visualize benchmark trends over time.

    Generates learning curves, model comparisons, and statistical analysis.
    """

    def __init__(self, storage: BenchmarkHistoryStorage):
        """
        Initialize trend analyzer.

        Args:
            storage: Benchmark history storage instance
        """
        self.storage = storage

    def extract_time_series(
        self, model_id: str | None = None, suite_name: str | None = None
    ) -> dict[str, list[tuple[datetime, float]]]:
        """
        Extract time series data from historical results.

        Args:
            model_id: Optional model ID filter
            suite_name: Optional suite name filter

        Returns:
            Dictionary mapping model IDs to lists of (timestamp, accuracy) tuples
        """
        results = self.storage.list_results(model_id=model_id, suite_name=suite_name)

        # Group by model_id
        time_series: dict[str, list[tuple[datetime, float]]] = {}

        for result in results:
            mid = result["model_id"]
            timestamp = datetime.fromisoformat(result["timestamp"])
            accuracy = result.get("accuracy")

            if accuracy is None:
                continue

            if mid not in time_series:
                time_series[mid] = []

            time_series[mid].append((timestamp, accuracy))

        # Sort each series by timestamp
        for mid in time_series:
            time_series[mid].sort(key=lambda x: x[0])

        logger.info(
            "time_series_extracted",
            models=len(time_series),
            total_points=sum(len(v) for v in time_series.values()),
        )

        return time_series

    def plot_learning_curve(
        self,
        model_id: str,
        suite_name: str | None = None,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Generate a learning curve plot for a single model.

        Args:
            model_id: Model ID to plot
            suite_name: Optional suite name filter
            output_path: Optional output path (defaults to generated path)

        Returns:
            Path to generated plot file
        """
        time_series = self.extract_time_series(model_id=model_id, suite_name=suite_name)

        if model_id not in time_series or not time_series[model_id]:
            raise ValueError(f"No data found for model '{model_id}'")

        data = time_series[model_id]
        timestamps, accuracies = zip(*data)

        # Create plot
        plt.figure(figsize=(10, 6))
        plt.plot(timestamps, accuracies, marker="o", linewidth=2, markersize=8)
        plt.xlabel("Time", fontsize=12)
        plt.ylabel("Accuracy", fontsize=12)
        plt.title(f"Learning Curve: {model_id}", fontsize=14, fontweight="bold")
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 1)

        # Format y-axis as percentage
        plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))

        plt.tight_layout()

        # Save plot
        if output_path is None:
            output_path = Path("results/benchmark") / f"learning_curve_{model_id.replace('/', '_')}.png"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info("learning_curve_plotted", model=model_id, path=str(output_path))

        return output_path

    def plot_model_comparison(
        self,
        model_ids: list[str] | None = None,
        suite_name: str | None = None,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Generate a comparison plot for multiple models.

        Args:
            model_ids: Optional list of model IDs to compare (all if None)
            suite_name: Optional suite name filter
            output_path: Optional output path

        Returns:
            Path to generated plot file
        """
        time_series = self.extract_time_series(suite_name=suite_name)

        if model_ids:
            time_series = {k: v for k, v in time_series.items() if k in model_ids}

        if not time_series:
            raise ValueError("No data found for comparison")

        # Create plot
        plt.figure(figsize=(12, 7))

        for model_id, data in time_series.items():
            if not data:
                continue

            timestamps, accuracies = zip(*data)
            plt.plot(timestamps, accuracies, marker="o", linewidth=2, markersize=6, label=model_id)

        plt.xlabel("Time", fontsize=12)
        plt.ylabel("Accuracy", fontsize=12)
        plt.title("Model Comparison", fontsize=14, fontweight="bold")
        plt.legend(loc="best", fontsize=10)
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 1)

        # Format y-axis as percentage
        plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))

        plt.tight_layout()

        # Save plot
        if output_path is None:
            output_path = Path("results/benchmark") / "model_comparison.png"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info(
            "model_comparison_plotted", models=len(time_series), path=str(output_path)
        )

        return output_path

    def calculate_statistics(
        self, model_id: str, suite_name: str | None = None
    ) -> dict[str, Any]:
        """
        Calculate statistical metrics for a model's performance.

        Args:
            model_id: Model ID to analyze
            suite_name: Optional suite name filter

        Returns:
            Dictionary containing statistical metrics
        """
        time_series = self.extract_time_series(model_id=model_id, suite_name=suite_name)

        if model_id not in time_series or not time_series[model_id]:
            raise ValueError(f"No data found for model '{model_id}'")

        data = time_series[model_id]
        accuracies = [acc for _, acc in data]

        stats = {
            "model_id": model_id,
            "data_points": len(accuracies),
            "mean_accuracy": float(np.mean(accuracies)),
            "std_dev": float(np.std(accuracies)),
            "min_accuracy": float(np.min(accuracies)),
            "max_accuracy": float(np.max(accuracies)),
        }

        # Calculate growth rate if we have at least 2 points
        if len(data) >= 2:
            first_acc = data[0][1]
            last_acc = data[-1][1]
            stats["growth_rate"] = float(last_acc - first_acc)
            stats["relative_growth"] = (
                float((last_acc - first_acc) / first_acc) if first_acc > 0 else 0.0
            )

        logger.info("statistics_calculated", model=model_id, stats=stats)

        return stats

    def compare_versions(
        self, model_ids: list[str], suite_name: str | None = None
    ) -> dict[str, Any]:
        """
        Compare performance across different model versions.

        Args:
            model_ids: List of model IDs to compare
            suite_name: Optional suite name filter

        Returns:
            Dictionary containing comparison metrics
        """
        comparison = {"models": {}}

        for model_id in model_ids:
            try:
                stats = self.calculate_statistics(model_id, suite_name)
                comparison["models"][model_id] = stats
            except ValueError:
                logger.warning("no_data_for_model", model=model_id)
                continue

        # Calculate pairwise differences
        if len(comparison["models"]) >= 2:
            models = list(comparison["models"].keys())
            comparison["pairwise_differences"] = []

            for i in range(len(models)):
                for j in range(i + 1, len(models)):
                    model_a = models[i]
                    model_b = models[j]

                    acc_a = comparison["models"][model_a]["mean_accuracy"]
                    acc_b = comparison["models"][model_b]["mean_accuracy"]

                    comparison["pairwise_differences"].append(
                        {
                            "model_a": model_a,
                            "model_b": model_b,
                            "accuracy_difference": acc_b - acc_a,
                            "relative_improvement": (
                                (acc_b - acc_a) / acc_a if acc_a > 0 else 0.0
                            ),
                        }
                    )

        logger.info("version_comparison_completed", models=len(comparison["models"]))

        return comparison
