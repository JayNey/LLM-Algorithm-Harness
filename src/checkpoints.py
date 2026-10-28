"""Atomic, private unit results shared by resumable business runners."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_checkpoint(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".checkpoint-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class UnitCheckpoint:
    """One immutable result per logical unit; refuse changed inputs on resume."""

    def __init__(self, root: Path, fingerprint: str):
        self.root = root
        manifest = root / "manifest.json"
        if manifest.exists():
            if json.loads(manifest.read_text(encoding="utf-8")) != {"fingerprint": fingerprint}:
                raise ValueError("Checkpoint inputs changed; cannot resume")
        else:
            write_checkpoint(manifest, {"fingerprint": fingerprint})

    def _path(self, key: str) -> Path:
        return self.root / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def put(self, key: str, result: dict[str, Any]) -> None:
        write_checkpoint(self._path(key), result)
