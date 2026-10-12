"""Dataset path resolution constrained to the configured data root.

API requests reference datasets by relative path (issue #156); resolving
them outside ``settings.DATA_ROOT`` would allow server-side arbitrary file
reads, so every dataset consumer goes through :func:`resolve_dataset_path`.
"""

from __future__ import annotations

from pathlib import Path

from api.config import settings


def resolve_dataset_path(raw: str) -> Path:
    """Resolve ``raw`` inside the data root, rejecting traversal."""
    root = Path(settings.DATA_ROOT).resolve()
    candidate = Path(raw)
    path = candidate if candidate.is_absolute() else root / candidate
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"dataset_path must stay under the data root: {settings.DATA_ROOT}")
    if not resolved.is_file():
        raise ValueError(f"dataset file is missing: {raw}")
    return resolved
