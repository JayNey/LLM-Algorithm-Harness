"""
Change detection and historical result loading for incremental evaluation.
"""

import json
from pathlib import Path

from src.incremental.fingerprint import EXECUTION_FINGERPRINT_VERSION
from src.incremental.history import IncrementalHistory, RunRecord
from src.models import ExecutionResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


def find_matching_run(
    history: IncrementalHistory,
    execution_fingerprint: str,
    *,
    source_run_id: str | None = None,
) -> RunRecord | None:
    """Select the newest compatible run, or the original source when resuming."""
    if not execution_fingerprint:
        return None
    for record in reversed(history.runs):
        if (
            type(record.fingerprint_version) is not int
            or record.fingerprint_version != EXECUTION_FINGERPRINT_VERSION
            or record.execution_fingerprint != execution_fingerprint
            or (source_run_id is not None and record.run_id != source_run_id)
        ):
            continue
        logger.info("compatible_incremental_run", run_id=record.run_id)
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


def should_use_incremental(
    changes: tuple[set[str], set[str], set[str]],
    current_fingerprint: dict[str, str] | None = None,
) -> bool:
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

    # Incremental only pays off when at least one unchanged problem exists
    # whose result can be reused; otherwise run the full evaluation.
    changed = len(added_ids) + len(modified_ids)
    total = len(current_fingerprint) if current_fingerprint else changed
    return total - changed > 0


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
            # All-or-nothing: a partially readable history would silently
            # produce a subset report, so any corrupt file disables reuse.
            logger.warning(f"Failed to read historical results {results_file}: {e}")
            return {}
        if not isinstance(data, list):
            logger.warning(f"Unexpected historical results shape in {results_file}")
            return {}

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
                    return {}

        if filtered_results:
            results[strategy] = filtered_results

    logger.debug(
        f"Loaded {sum(len(v) for v in results.values())}/{len(problem_ids)} "
        f"historical results from {result_path}"
    )
    return results
