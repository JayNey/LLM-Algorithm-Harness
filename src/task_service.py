"""Persistent, local task orchestration for long-running evaluations.

The service deliberately owns lifecycle and persistence only.  A caller supplies
the unit worker, so CLI, Web, and desktop clients can share the same task
semantics without duplicating evaluation logic.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.utils.secrets import redact_sensitive_data

TaskState = Literal["queued", "running", "completed", "failed", "cancelled"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskUnit(BaseModel):
    """One strategy/problem/repetition unit in a task."""

    unit_id: str
    strategy: str
    problem_id: str
    model_id: str = ""
    repeat_index: int = Field(0, ge=0)
    status: TaskState = "queued"
    uncertain: bool = False
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class TaskEvent(BaseModel):
    """Append-only event suitable for polling or SSE adapters."""

    sequence: int = Field(..., ge=1)
    run_id: str
    kind: str
    state: TaskState
    timestamp: str
    unit_id: str | None = None
    strategy: str | None = None
    problem_id: str | None = None
    completed_units: int = Field(0, ge=0)
    total_units: int = Field(0, ge=0)
    message: str | None = None
    uncertain: bool = False


class TaskRecord(BaseModel):
    """Durable task state and its event history."""

    run_id: str
    state: TaskState = "queued"
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    config_fingerprint: str
    dataset_fingerprint: str
    total_units: int = Field(..., ge=0)
    completed_units: int = Field(0, ge=0)
    cancel_requested: bool = False
    error: str | None = None
    units: list[TaskUnit] = Field(default_factory=list)
    events: list[TaskEvent] = Field(default_factory=list)


class TaskStore:
    """Atomic JSON persistence for local single-user task state."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def path_for(self, run_id: str) -> Path:
        if not run_id or Path(run_id).name != run_id or "/" in run_id or "\\" in run_id:
            raise ValueError("Invalid run_id")
        return self.root / f"{run_id}.json"

    def save(self, record: TaskRecord) -> None:
        """Atomically replace the task file so interrupted writes do not corrupt it."""
        target = self.path_for(record.run_id)
        payload = record.model_dump(mode="json")
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        with self._lock:
            try:
                with temporary.open("w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

    def load(self, run_id: str) -> TaskRecord:
        path = self.path_for(run_id)
        try:
            with path.open("r", encoding="utf-8") as stream:
                return TaskRecord.model_validate(json.load(stream))
        except FileNotFoundError:
            raise FileNotFoundError(f"Task '{run_id}' was not found") from None

    def list(self) -> builtins.list[TaskRecord]:
        records = []
        for path in sorted(self.root.glob("*.json")):
            try:
                records.append(TaskRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                # A malformed file is not silently turned into a task.  It is
                # ignored by listing and can be diagnosed from the file itself.
                continue
        return records


Worker = Callable[[TaskUnit], Any]


class TaskService:
    """Run persisted units with bounded concurrency and resumable semantics."""

    def __init__(self, root: str | Path):
        self.store = TaskStore(root)
        self._cancel_events: dict[str, threading.Event] = {}
        self._cancel_lock = threading.RLock()

    @staticmethod
    def config_fingerprint(config: Any) -> str:
        """Hash a redacted, canonical config snapshot."""
        if hasattr(config, "redacted_dict"):
            payload = config.redacted_dict()
        elif hasattr(config, "model_dump"):
            payload = redact_sensitive_data(config.model_dump(mode="json"))
        else:
            payload = redact_sensitive_data(config)
        # Keep credentials out of the record while still invalidating a task
        # when the credential used for a resume has changed.
        llm_config = getattr(config, "llm_config", None)
        api_key = getattr(llm_config, "api_key", None)
        if hasattr(api_key, "get_secret_value"):
            raw_key = api_key.get_secret_value()
            payload = dict(payload)
            payload["llm_api_key_fingerprint"] = hashlib.sha256(
                raw_key.encode("utf-8")
            ).hexdigest()
        return TaskService._hash_json(payload)

    @staticmethod
    def dataset_fingerprint(path: str | Path) -> str:
        """Hash a file or deterministic directory manifest."""
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"Dataset path does not exist: {target}")
        digest = hashlib.sha256()
        if target.is_file():
            digest.update(target.read_bytes())
            return digest.hexdigest()
        for child in sorted(p for p in target.rglob("*") if p.is_file()):
            digest.update(str(child.relative_to(target)).encode("utf-8"))
            digest.update(child.read_bytes())
        return digest.hexdigest()

    @staticmethod
    def _hash_json(payload: Any) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def create(
        self,
        *,
        units: Iterable[TaskUnit],
        config_fingerprint: str,
        dataset_fingerprint: str,
        run_id: str | None = None,
    ) -> TaskRecord:
        """Create and persist a queued task."""
        materialized = list(units)
        identifier = run_id or f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        if self.store.path_for(identifier).exists():
            raise ValueError(f"Task '{identifier}' already exists")
        record = TaskRecord(
            run_id=identifier,
            config_fingerprint=config_fingerprint,
            dataset_fingerprint=dataset_fingerprint,
            total_units=len(materialized),
            units=materialized,
        )
        self._append_event(record, "task_created", message="Task queued")
        self.store.save(record)
        return record

    def get(self, run_id: str) -> TaskRecord:
        return self.store.load(run_id)

    def list(self) -> builtins.list[TaskRecord]:
        return self.store.list()

    def events_since(self, run_id: str, sequence: int = 0) -> builtins.list[TaskEvent]:
        """Return ordered events after a sequence number for polling/SSE adapters."""
        if sequence < 0:
            raise ValueError("sequence must be non-negative")
        return [event for event in self.store.load(run_id).events if event.sequence > sequence]

    def cancel(self, run_id: str) -> TaskRecord:
        """Compatibility alias for clients that expose a cancel action."""
        return self.request_cancel(run_id)

    def fail(self, run_id: str, error: str) -> TaskRecord:
        """Persist a task-level setup failure before any unit is dispatched."""
        record = self.store.load(run_id)
        record.state = "failed"
        record.error = error
        record.updated_at = _now()
        self._append_event(record, "task_failed", message=error)
        self.store.save(record)
        return record

    def request_cancel(self, run_id: str) -> TaskRecord:
        """Request cancellation; running workers are marked uncertain on exit."""
        record = self.store.load(run_id)
        if record.state in {"completed", "failed", "cancelled"}:
            return record
        record.cancel_requested = True
        record.updated_at = _now()
        with self._cancel_lock:
            event = self._cancel_events.setdefault(run_id, threading.Event())
            event.set()
        self._append_event(record, "cancel_requested", message="Cancellation requested")
        self.store.save(record)
        return record

    def run(
        self,
        run_id: str,
        worker: Worker,
        *,
        max_workers: int = 1,
        config_fingerprint: str | None = None,
        dataset_fingerprint: str | None = None,
        resume: bool = False,
    ) -> TaskRecord:
        """Execute queued units, or resume a compatible interrupted task."""
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        record = self.store.load(run_id)
        self._validate_resume_fingerprints(
            record, config_fingerprint=config_fingerprint, dataset_fingerprint=dataset_fingerprint
        )
        if record.state in {"completed", "failed", "cancelled"} and not resume:
            raise ValueError(f"Task '{run_id}' is already terminal; pass resume=True to continue")
        if resume:
            self._prepare_resume(record)
            # Clear the persisted cancellation latch before a deliberate
            # resume; otherwise the merge guard below would cancel it again.
            self.store.save(record)

        with self._cancel_lock:
            cancel_event = self._cancel_events.setdefault(run_id, threading.Event())
            if record.cancel_requested:
                cancel_event.set()
        record.cancel_requested = False
        record.state = "running"
        record.error = None
        record.updated_at = _now()
        self._append_event(record, "task_started", message="Task running")
        self._save_with_external_events(record)

        executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=f"task-{run_id}")
        pending: dict[Future[Any], TaskUnit] = {}
        queue = [unit for unit in record.units if unit.status == "queued"]
        detached_executor = False
        try:
            while queue or pending:
                persisted_record = self.store.load(run_id)
                if len(persisted_record.events) > len(record.events):
                    record.events = persisted_record.events
                persisted_cancel = persisted_record.cancel_requested
                if cancel_event.is_set() or record.cancel_requested or persisted_cancel:
                    record.cancel_requested = True
                    for unit in queue:
                        self._mark_cancelled(record, unit, uncertain=False, message="Not dispatched")
                    queue.clear()
                    for unit in pending.values():
                        self._mark_cancelled(record, unit, uncertain=True, message="In-flight request uncertain")
                    pending.clear()
                    record.state = "cancelled"
                    record.updated_at = _now()
                    self._append_event(record, "task_cancelled", message="Task cancelled")
                    self._save_with_external_events(record)
                    executor.shutdown(wait=False, cancel_futures=True)
                    detached_executor = True
                    return record

                while queue and len(pending) < max_workers and not cancel_event.is_set():
                    if self.store.load(run_id).cancel_requested:
                        break
                    unit = queue.pop(0)
                    unit.status = "running"
                    unit.started_at = _now()
                    unit.error = None
                    record.updated_at = _now()
                    self._append_event(record, "unit_started", unit=unit)
                    self._save_with_external_events(record)
                    pending[executor.submit(worker, unit.model_copy(deep=True))] = unit

                if not pending:
                    continue
                # Poll briefly so an external cancel request is observed even
                # while a provider or sandbox call is still in flight.
                done, _ = wait(tuple(pending), timeout=0.1, return_when=FIRST_COMPLETED)
                if not done:
                    continue
                for future in done:
                    unit = pending.pop(future)
                    try:
                        result = future.result()
                        unit.result = self._serialize_result(result)
                        unit.status = "completed"
                        unit.uncertain = False
                        self._append_event(record, "unit_completed", unit=unit)
                    except Exception as exc:
                        unit.status = "failed"
                        unit.error = str(exc)
                        record.error = record.error or unit.error
                        self._append_event(record, "unit_failed", unit=unit, message=unit.error)
                    unit.finished_at = _now()
                    record.completed_units = sum(
                        1 for candidate in record.units if candidate.status in {"completed", "failed"}
                    )
                    record.updated_at = _now()
                    self._save_with_external_events(record)

            record.state = "completed" if all(unit.status == "completed" for unit in record.units) else "failed"
            record.completed_units = sum(
                1 for unit in record.units if unit.status in {"completed", "failed"}
            )
            record.updated_at = _now()
            self._append_event(record, "task_finished", message=f"Task {record.state}")
            self._save_with_external_events(record)
            return record
        finally:
            if detached_executor:
                pass
            elif pending:
                executor.shutdown(wait=False, cancel_futures=True)
            else:
                executor.shutdown(wait=True)
            with self._cancel_lock:
                self._cancel_events.pop(run_id, None)

    def _validate_resume_fingerprints(
        self,
        record: TaskRecord,
        *,
        config_fingerprint: str | None,
        dataset_fingerprint: str | None,
    ) -> None:
        if config_fingerprint and config_fingerprint != record.config_fingerprint:
            raise ValueError("Task configuration fingerprint does not match; refusing resume")
        if dataset_fingerprint and dataset_fingerprint != record.dataset_fingerprint:
            raise ValueError("Dataset fingerprint does not match; refusing resume")

    def _save_with_external_events(self, record: TaskRecord) -> None:
        """Merge a concurrent cancel event before replacing the JSON record."""
        try:
            persisted = self.store.load(record.run_id)
        except FileNotFoundError:
            persisted = None
        if persisted is not None:
            if len(persisted.events) > len(record.events):
                record.events = persisted.events
            if persisted.cancel_requested:
                record.cancel_requested = True
        self.store.save(record)

    def _prepare_resume(self, record: TaskRecord) -> None:
        """Requeue only unfinished or uncertain units; keep confirmed terminal units."""
        for unit in record.units:
            if unit.uncertain or unit.status in {"running", "cancelled"}:
                unit.status = "queued"
                unit.uncertain = False
                unit.result = None
                unit.error = None
                unit.started_at = None
                unit.finished_at = None
        record.cancel_requested = False
        record.completed_units = sum(
            1 for unit in record.units if unit.status in {"completed", "failed"}
        )

    def _mark_cancelled(
        self, record: TaskRecord, unit: TaskUnit, *, uncertain: bool, message: str
    ) -> None:
        unit.status = "cancelled"
        unit.uncertain = uncertain
        unit.finished_at = _now()
        self._append_event(record, "unit_cancelled", unit=unit, message=message)

    def _append_event(
        self,
        record: TaskRecord,
        kind: str,
        *,
        unit: TaskUnit | None = None,
        message: str | None = None,
    ) -> None:
        sequence = len(record.events) + 1
        event = TaskEvent(
            sequence=sequence,
            run_id=record.run_id,
            kind=kind,
            state=record.state,
            timestamp=_now(),
            unit_id=unit.unit_id if unit else None,
            strategy=unit.strategy if unit else None,
            problem_id=unit.problem_id if unit else None,
            completed_units=record.completed_units,
            total_units=record.total_units,
            message=message,
            uncertain=unit.uncertain if unit else False,
        )
        record.events.append(event)

    @staticmethod
    def _serialize_result(result: Any) -> dict[str, Any]:
        if isinstance(result, BaseModel):
            return redact_sensitive_data(result.model_dump(mode="json"))
        if isinstance(result, dict):
            return redact_sensitive_data(result)
        raise TypeError("Task worker must return a dict or Pydantic model")
