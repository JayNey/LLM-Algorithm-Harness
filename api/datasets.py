"""Dataset path resolution constrained to the configured data root.

API requests reference datasets by relative path (issue #156); resolving
them outside ``settings.DATA_ROOT`` would allow server-side arbitrary file
reads, so every dataset consumer goes through :func:`resolve_dataset_path`.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.auth.service import AuthService
from api.config import settings
from api.files.store import FileStore
from src.models import Problem


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


# Personal collections are already durable, owner-scoped data; uploads are only
# an import transport and are deliberately not execution references.
def personal_dataset_id(owner_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"harness:personal-dataset:{owner_id}"))


def list_datasets(store: FileStore, owner_id: str) -> list[dict[str, Any]]:
    with store.connection() as db:
        row = db.execute(
            "SELECT payload, updated_at FROM api_file_datasets WHERE user_id=?", (owner_id,)
        ).fetchone()
    if row is None:
        return []
    try:
        data = json.loads(row["payload"])
        if not isinstance(data, list):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Personal dataset is unavailable") from None
    return [
        {
            "id": personal_dataset_id(owner_id),
            "name": "Personal problem collection",
            "problem_count": len(data),
            "updated_at": row["updated_at"],
        }
    ]


def _encoded(data: Any) -> bytes:
    return json.dumps(
        data, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def freeze_dataset(
    dataset_id: str | None,
    dataset_path: str | None,
    owner_id: str,
    auth: AuthService,
) -> dict[str, Any]:
    """Freeze once before business persistence; no external snapshot files."""
    if (dataset_id is None) == (dataset_path is None):
        raise ValueError("Provide exactly one of dataset_id or dataset_path")
    if dataset_id is not None:
        if dataset_id != personal_dataset_id(owner_id):
            raise ValueError("Dataset not found")
        store = FileStore(auth.store)
        with store.connection() as db:
            row = db.execute(
                "SELECT payload FROM api_file_datasets WHERE user_id=?", (owner_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Dataset not found")
        raw = row["payload"]
    else:
        try:
            raw = resolve_dataset_path(dataset_path or "").read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise ValueError("Dataset is unavailable") from None
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("Dataset must be a JSON array")
        if not data:
            raise ValueError("Dataset is empty")
        # Validate every record without silently dropping invalid problems.
        problems = [Problem.model_validate(value).model_dump(mode="json") for value in data]
        encoded = _encoded(problems)
    except (ValueError, TypeError) as exc:
        if str(exc) in {"Dataset must be a JSON array", "Dataset is empty"}:
            raise
        raise ValueError("Dataset is unavailable: invalid problem data") from None
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "owner_id": owner_id,
        "dataset_id": dataset_id,
        "dataset_path": dataset_path,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "problem_count": len(problems),
        "problems": problems,
    }


def snapshot_summary(config: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = config.get("dataset_snapshot")
    if snapshot is None:
        return None
    return {key: value for key, value in snapshot.items() if key not in {"problems", "owner_id"}}


def public_dataset_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        **config,
        **({"dataset_snapshot": snapshot_summary(config)} if "dataset_snapshot" in config else {}),
    }


@contextmanager
def execution_dataset(config: dict[str, Any], owner_id: str) -> Iterator[str]:
    """Materialize a private local file for this attempt, cleaning up on exit.

    The shared business database, not an expiring upload or shared filesystem,
    is the source of truth. Existing pre-snapshot jobs retain legacy behavior.
    """
    snapshot = config.get("dataset_snapshot")
    if snapshot is None:
        if config.get("dataset_id"):
            raise ValueError("Dataset snapshot is unavailable")
        yield str(resolve_dataset_path(config["dataset_path"]))
        return
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("owner_id") != owner_id
        or snapshot.get("schema_version") != 1
    ):
        raise ValueError("Dataset snapshot is unavailable for this owner")
    try:
        data = snapshot["problems"]
        encoded = _encoded(data)
        valid = (
            isinstance(data, list)
            and bool(data)
            and len(data) == snapshot.get("problem_count")
            and hashlib.sha256(encoded).hexdigest() == snapshot.get("sha256")
        )
    except (KeyError, ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError("Dataset snapshot integrity check failed")
    with tempfile.TemporaryDirectory(prefix="harness-dataset-") as directory:
        path = Path(directory) / "problems.json"
        path.write_bytes(encoded)
        yield str(path)
