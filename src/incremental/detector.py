"""
Change detection and historical result loading for incremental evaluation.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

from src.incremental.history import IncrementalHistory, RunRecord
from src.models import ExecutionResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


def find_matching_run(
    history: IncrementalHistory,
    current_fingerprint: Dict[str, str],
    strategy: str,
    model: str,
) -> Optional[RunRecord]:
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
        if record.dataset_fingerprint == current_fingerprint:
            logger.info(
                f"Found matching run: {record.run_id} "
                f"(strategy={strategy}, model={model}, {len(current_fingerprint)} problems)"
            )
            return record

    return None


def detect_changes(
    current_fingerprint: Dict[str, str],
    historical_fingerprint: Dict[str, str],
) -> Tuple[Set[str], Set[str], Set[str]]:
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


def should_use_incremental(changes: Tuple[Set[str], Set[str], Set[str]]) -> bool:
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

    # If nothing changed, incremental is beneficial
    if not added_ids and not modified_ids:
        return True

    # If there are changes, incremental is still useful
    # (The actual decision is usually made by the caller based on whether
    # a matching run exists, but this helper can be used for additional checks)
    return True


def load_historical_results(
    result_path: Path, problem_ids: Set[str]
) -> Dict[str, ExecutionResult]:
    """
    Load historical execution results for specific problem IDs.

    Args:
        result_path: Path to historical result JSON file
        problem_ids: Set of problem IDs to extract

    Returns:
        Dict mapping problem_id to ExecutionResult (only for successfully loaded problems)

    Raises:
        FileNotFoundError: If result file does not exist
        json.JSONDecodeError: If result file is not valid JSON
    """
    if not result_path.exists():
        raise FileNotFoundError(f"Historical result file not found: {result_path}")

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Extract results for the requested problem IDs
        results = {}
        for result_data in data.get("results", []):
            problem_id = result_data.get("problem_id")
            if problem_id in problem_ids:
                # Reconstruct ExecutionResult from dict
                results[problem_id] = ExecutionResult(**result_data)

        logger.debug(f"Loaded {len(results)}/{len(problem_ids)} historical results from {result_path}")
        return results

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse result file {result_path}: {e}")
        raise
    except (TypeError, KeyError) as e:
        logger.error(f"Invalid result file structure in {result_path}: {e}")
        raise
