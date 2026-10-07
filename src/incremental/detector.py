"""
Change detection and historical result loading for incremental evaluation.
"""

import json
from pathlib import Path

from src.incremental.history import IncrementalHistory, RunRecord
from src.models import ExecutionResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


def find_matching_run(
    history: IncrementalHistory,
    current_fingerprint: dict[str, str],
    strategy: str,
    model: str,
) -> RunRecord | None:
    """
    Find a historical run that matches the current evaluation parameters.

    Matching criteria:
    - Strategy name must match
    - Model name must match
    - Dataset fingerprint must match

    Args:
        history: Historical run records
        current_fingerprint: Current dataset fingerprint mapping
        strategy: Current strategy name
        model: Current model name

    Returns:
        Matching RunRecord if found, None otherwise
    """
    for record in reversed(history.runs):  # Search newest first
        if record.strategy != strategy:
            continue
        if record.model != model:
            continue
        # Strategy and model match. The dataset fingerprint may differ —
        # that is the whole point of incremental evaluation; detect_changes
        # quantifies the diff and should_use_incremental rejects changes
        # that are too large for reuse to pay off.
        logger.info(
            f"Found matching run: {record.run_id} "
            f"(strategy={strategy}, model={model}, "
            f"{len(record.dataset_fingerprint or {})} historical problems)"
        )
        return record

    return None


def detect_changes(
    current_fingerprint: dict[str, str],
    historical_fingerprint: dict[str, str],
) -> tuple[set[str], set[str], set[str]]:
    """
    Detect changes between current and historical datasets.

    Args:
        current_fingerprint: Current problem_id -> fingerprint mapping
        historical_fingerprint: Historical problem_id -> fingerprint mapping

    Returns:
        Tuple of (added_ids, modified_ids, deleted_ids)
        - added_ids: Problem IDs present in current but not in historical
        - modified_ids: Problem IDs present in both but with different fingerprints
        - deleted_ids: Problem IDs present in historical but not in current
    """
    current_ids = set(current_fingerprint.keys())
    historical_ids = set(historical_fingerprint.keys())

    added_ids = current_ids - historical_ids
    deleted_ids = historical_ids - current_ids

    # Check for modified problems (same ID, different fingerprint)
    common_ids = current_ids & historical_ids
    modified_ids = {
        pid for pid in common_ids if current_fingerprint[pid] != historical_fingerprint[pid]
    }

    return added_ids, modified_ids, deleted_ids


def should_use_incremental(changes: tuple[set[str], set[str], set[str]]) -> bool:
    """
    Determine whether incremental evaluation is beneficial.

    Heuristic: Use incremental mode if there are additions or modifications
    but the change is not overwhelming (e.g., < 100% of dataset changed).

    Args:
        changes: Tuple of (added_ids, modified_ids, deleted_ids)

    Returns:
        True if incremental evaluation should be used, False otherwise
    """
    added_ids, modified_ids, deleted_ids = changes

    # If nothing changed, no need for incremental
    if not added_ids and not modified_ids and not deleted_ids:
        return False

    # If there are changes, incremental is useful
    return True


def load_historical_results(
    result_path: Path, problem_ids: set[str]
) -> dict[str, list[ExecutionResult]]:
    """
    Load historical execution results for specific problem IDs.

    Args:
        result_path: Path to the historical run directory (per-strategy
            ``<strategy>_results.json`` files are read from it)
        problem_ids: Set of problem IDs to extract

    Returns:
        Dict mapping strategy to list of ExecutionResults (only for successfully loaded problems)
        Returns empty dict if the directory doesn't exist or has errors
    """
    run_dir = Path(result_path)
    if not run_dir.exists():
        logger.info(f"Historical result directory not found: {result_path}")
        return {}

    results: dict[str, list[ExecutionResult]] = {}
    for results_file in sorted(run_dir.glob("*_results.json")):
        strategy = results_file.name[: -len("_results.json")]
        if not strategy:
            continue
        try:
            with open(results_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning(f"Failed to read historical results {results_file}: {e}")
            continue
        if not isinstance(data, list):
            logger.warning(f"Unexpected historical results shape in {results_file}")
            continue

        filtered_results = []
        for result_data in data:
            if not isinstance(result_data, dict):
                continue
            problem_id = result_data.get("problem_id")
            if problem_id in problem_ids:
                # Reconstruct ExecutionResult from dict, adding source="reused"
                result_dict = {**result_data, "source": "reused"}
                try:
                    filtered_results.append(ExecutionResult(**result_dict))
                except Exception as e:
                    logger.warning(f"Skipping unreadable historical result in {results_file}: {e}")

        if filtered_results:
            results[strategy] = filtered_results

    logger.debug(
        f"Loaded {sum(len(v) for v in results.values())}/{len(problem_ids)} "
        f"historical results from {result_path}"
    )
    return results
