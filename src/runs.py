"""
Run-state visibility helpers for checkpoint resume management (issue #88).

TaskService already persists every run as ``output_dir/tasks/<run_id>.json``
with durable unit state; this module derives the operational view on top:
per-run progress and accumulated known-pricing cost for ``harness runs
list``, matching of unfinished runs for the startup hint, and completed-run
cleanup.

Cost accounting reuses ``cost_strategy.result_cost``: only traces with
known pricing and known usage count toward the total; results with unknown
usage are counted separately.
"""

from typing import Any, Dict, List

from src.cost_strategy import result_cost
from src.models import ExecutionResult
from src.task_service import TaskRecord, TaskService

# Only a fully completed run has nothing left to resume; failed and
# cancelled runs requeue their unfinished or uncertain units on --resume.
FINISHED_STATES = {"completed"}


def summarize_run(record: TaskRecord) -> Dict[str, Any]:
    """Derive the operational view of one persisted run."""
    known_cost = 0.0
    unknown_usage = 0
    for unit in record.units:
        if unit.result is None:
            continue
        result = ExecutionResult.model_validate(unit.result)
        cost, usage_unknown = result_cost(result)
        known_cost += float(cost)
        if usage_unknown:
            unknown_usage += 1
    return {
        "run_id": record.run_id,
        "state": record.state,
        "completed": record.completed_units,
        "total": record.total_units,
        "updated_at": record.updated_at,
        "resumable": record.state not in FINISHED_STATES,
        "cost_usd": round(known_cost, 6),
        "unknown_usage_results": unknown_usage,
    }


def find_matching_unfinished(
    service: TaskService,
    config_fingerprint: str,
    dataset_fingerprint: str,
) -> List[TaskRecord]:
    """Unfinished runs whose config and dataset fingerprints both match."""
    matches = [
        record
        for record in service.list()
        if record.state not in FINISHED_STATES
        and record.config_fingerprint == config_fingerprint
        and record.dataset_fingerprint == dataset_fingerprint
    ]
    matches.sort(key=lambda record: record.updated_at, reverse=True)
    return matches
