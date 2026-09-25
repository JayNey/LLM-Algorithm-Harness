"""Historical benchmark results storage and management."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


class BenchmarkHistoryStorage:
    """
    Manage historical benchmark evaluation results.

    Stores results as JSON files with naming pattern:
    {timestamp}_{model-id}.json
    """

    def __init__(self, storage_dir: str | Path = "results/benchmark"):
        """
        Initialize history storage.

        Args:
            storage_dir: Directory to store benchmark results
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info("benchmark_storage_initialized", path=str(self.storage_dir))

    def save_result(
        self,
        suite_name: str,
        model_id: str,
        results: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> Path:
        """
        Save benchmark evaluation result.

        Args:
            suite_name: Name of the benchmark suite
            model_id: LLM model identifier
            results: Evaluation results dictionary
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Path to saved result file
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Format timestamp as YYYYMMDD-HHMMSS
        timestamp_str = timestamp.strftime("%Y%m%d-%H%M%S")

        # Sanitize model_id for filename
        safe_model_id = model_id.replace("/", "_").replace(":", "_")

        # Create filename
        filename = f"{timestamp_str}_{safe_model_id}.json"
        filepath = self.storage_dir / filename

        # Prepare data with metadata
        data = {
            "timestamp": timestamp.isoformat(),
            "suite_name": suite_name,
            "model_id": model_id,
            "results": results,
        }

        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(
            "benchmark_result_saved",
            suite=suite_name,
            model=model_id,
            path=str(filepath),
        )

        return filepath

    def load_result(self, filepath: str | Path) -> dict[str, Any]:
        """
        Load a benchmark result from file.

        Args:
            filepath: Path to result file

        Returns:
            Dictionary containing result data

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid
        """
        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"Result file not found: {filepath}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in result file: {e}")

    def list_results(
        self,
        model_id: str | None = None,
        suite_name: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        List and filter historical benchmark results.

        Args:
            model_id: Optional model ID filter
            suite_name: Optional suite name filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of result metadata dictionaries
        """
        results = []

        # Iterate through all JSON files
        for filepath in sorted(self.storage_dir.glob("*.json")):
            try:
                data = self.load_result(filepath)

                # Apply filters
                if model_id and data.get("model_id") != model_id:
                    continue

                if suite_name and data.get("suite_name") != suite_name:
                    continue

                # Parse timestamp for date filtering
                result_timestamp = datetime.fromisoformat(data.get("timestamp", ""))

                if start_date and result_timestamp < start_date:
                    continue

                if end_date and result_timestamp > end_date:
                    continue

                # Include result
                results.append(
                    {
                        "filepath": str(filepath),
                        "timestamp": data.get("timestamp"),
                        "suite_name": data.get("suite_name"),
                        "model_id": data.get("model_id"),
                        "accuracy": self._extract_accuracy(data),
                    }
                )

            except (FileNotFoundError, ValueError, KeyError) as e:
                logger.warning("failed_to_load_result", path=str(filepath), error=str(e))
                continue

        return results

    def _extract_accuracy(self, data: dict[str, Any]) -> float | None:
        """
        Extract overall accuracy from result data.

        Args:
            data: Result data dictionary

        Returns:
            Average accuracy across strategies, or None if unavailable
        """
        try:
            results = data.get("results", {})
            strategies = results.get("strategies", {})

            if not strategies:
                return None

            accuracies = [
                s.get("accuracy", 0.0) for s in strategies.values() if "accuracy" in s
            ]

            if not accuracies:
                return None

            return sum(accuracies) / len(accuracies)

        except Exception:
            return None
