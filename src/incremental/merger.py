"""Result merging for incremental evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.incremental.history import IncrementalHistory, RunRecord
from src.models import ExecutionResult


def merge_results(
    new_results: dict[str, list[ExecutionResult]],
    historical_results: dict[str, list[ExecutionResult]],
) -> dict[str, list[ExecutionResult]]:
    """
    Merge new evaluation results with historical results.

    Args:
        new_results: Results from current evaluation (by strategy name)
        historical_results: Results from historical run (by strategy name)

    Returns:
        Merged results containing both new and historical results
    """
    merged = {}

    for strategy_name, new_strategy_results in new_results.items():
        # Get historical results for this strategy
        historical_strategy_results = historical_results.get(strategy_name, [])

        # Create a map of problem_id -> result for quick lookup
        new_by_id = {r.problem_id: r for r in new_strategy_results}
        historical_by_id = {r.problem_id: r for r in historical_strategy_results}

        # Merge: prefer new results, fallback to historical
        all_problem_ids = set(new_by_id.keys()) | set(historical_by_id.keys())
        merged_strategy_results = []

        for problem_id in sorted(all_problem_ids):
            if problem_id in new_by_id:
                # Use new result
                result = new_by_id[problem_id]
                # Mark as evaluated
                if hasattr(result, "metadata") and isinstance(result.metadata, dict):
                    result.metadata["source"] = "evaluated"
                merged_strategy_results.append(result)
            else:
                # Use historical result
                result = historical_by_id[problem_id]
                # Mark as reused
                if hasattr(result, "metadata") and isinstance(result.metadata, dict):
                    result.metadata["source"] = "reused"
                merged_strategy_results.append(result)

        merged[strategy_name] = merged_strategy_results

    return merged


def load_historical_results_from_summary(
    result_path: Path, problem_ids: set[str]
) -> dict[str, list[ExecutionResult]]:
    """
    Load historical results from a summary.json file.

    Args:
        result_path: Path to summary.json or results directory
        problem_ids: Set of problem IDs to load

    Returns:
        Dict mapping strategy name to list of ExecutionResult objects
    """
    # Handle both summary.json and directory paths
    if result_path.is_dir():
        summary_path = result_path / "summary.json"
    else:
        summary_path = result_path

    if not summary_path.exists():
        return {}

    try:
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

        # Load strategy results from individual files
        results_by_strategy = {}
        result_dir = summary_path.parent

        for strategy_name in summary.get("strategies", {}).keys():
            results_file = result_dir / f"{strategy_name}_results.json"
            if not results_file.exists():
                continue

            with open(results_file, encoding="utf-8") as f:
                results_data = json.load(f)

            # Filter to requested problem IDs and convert to ExecutionResult
            filtered_results = []
            for result_dict in results_data:
                if result_dict.get("problem_id") in problem_ids:
                    # Ensure metadata field exists
                    if "metadata" not in result_dict:
                        result_dict["metadata"] = {}
                    # Convert dict to ExecutionResult
                    result = ExecutionResult(**result_dict)
                    filtered_results.append(result)

            results_by_strategy[strategy_name] = filtered_results

        return results_by_strategy

    except (json.JSONDecodeError, KeyError, IOError) as e:
        # Log error but don't fail
        print(f"Warning: Failed to load historical results from {result_path}: {e}")
        return {}


def update_incremental_history(
    history: IncrementalHistory,
    history_path: Path,
    dataset_fingerprint: dict[str, str],
    result_path: str,
    strategy: str,
    model: str,
) -> None:
    """
    Update incremental history with a new run record.

    Args:
        history: Current incremental history
        history_path: Path to save history
        dataset_fingerprint: Fingerprint of the dataset
        result_path: Path to the result directory
        strategy: Strategy name
        model: Model name
    """
    from datetime import datetime, timezone

    # Create new run record
    run_record = RunRecord(
        run_id=Path(result_path).parent.name if "/" in result_path else "unknown",
        timestamp=datetime.now(timezone.utc).isoformat(),
        strategy=strategy,
        model=model,
        dataset_fingerprint=dataset_fingerprint,
        result_path=result_path,
    )

    # Add to history
    history.add_run(run_record)

    # Save history
    history.save(history_path)
