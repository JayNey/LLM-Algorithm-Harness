"""Shared results root for experiment and A/B artifacts.

The API and every Celery worker must resolve experiment/A-B outputs and
checkpoints to the same directory even when they run in different containers
or with different working directories. ``RESULTS_ROOT`` is therefore resolved
against the repository root, not the process cwd.
"""

from __future__ import annotations

import os
from pathlib import Path

from api.config import settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def results_root() -> Path:
    """Return the configured results root as an absolute path."""
    configured = Path(settings.RESULTS_ROOT).expanduser()
    if not configured.is_absolute():
        configured = REPO_ROOT / configured
    return configured.resolve()


def ensure_results_root() -> Path:
    """Create the results root and fail fast when it is not writable."""
    root = results_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / f".write-probe-{os.getpid()}"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise RuntimeError(f"RESULTS_ROOT is not writable: {root} ({exc})") from exc
    return root


def resolve_results_path(stored: str | Path) -> Path:
    """Resolve a stored artifact path against the shared results root.

    New records store absolute paths. Historical rows stored worker-relative
    paths such as ``results/experiments/api/<id>``; those are re-rooted so an
    API process with another cwd can still read the shared volume.
    """
    path = Path(stored).expanduser()
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == "results":
        parts = parts[1:]
    return results_root().joinpath(*parts)
