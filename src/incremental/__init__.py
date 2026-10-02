"""
Incremental evaluation module for LLM Algorithm Harness.

This module provides incremental evaluation capabilities to avoid re-running
evaluations on unchanged problems by detecting dataset changes and reusing
historical results.
"""

from src.incremental.detector import (
    detect_changes,
    find_matching_run,
    load_historical_results,
    should_use_incremental,
)
from src.incremental.fingerprint import compute_dataset_fingerprint, compute_problem_fingerprint
from src.incremental.history import IncrementalHistory, RunRecord

__all__ = [
    "compute_problem_fingerprint",
    "compute_dataset_fingerprint",
    "RunRecord",
    "IncrementalHistory",
    "find_matching_run",
    "detect_changes",
    "should_use_incremental",
    "load_historical_results",
]
