"""Committed snapshots and fenced, recoverable publication across two databases."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import (
    AsyncTask,
    Evaluation,
    EvaluationArtifactPublication,
    EvaluationResult,
    utcnow,
)
from api.files.service import FileService, json_bytes
from src.task_manager import TaskManager
from src.utils.secrets import redact_sensitive_data

logger = logging.getLogger(__name__)


def _owned(db: Session, evaluation_id: str, owner: str, *, lock: bool = False) -> Evaluation:
    row = db.get(Evaluation, evaluation_id)
    if row is None or row.user_id != owner:
        raise HTTPException(404, "Result not found")
    if lock:
        task = db.get(AsyncTask, row.async_task_id) if row.async_task_id else None
        if task is not None:
            TaskManager(db)._lock_business_task(task)
        # Also lock evaluations without AsyncTask (legacy completed evaluations).
        db.execute(
            update(Evaluation)
            .where(Evaluation.id == evaluation_id)
            .values(id=Evaluation.id, updated_at=Evaluation.updated_at)
            .execution_options(synchronize_session=False)
        )
        db.refresh(row)
        if row.user_id != owner:
            raise HTTPException(404, "Result not found")
    return row


def stage_publication(db: Session, evaluation: Evaluation) -> EvaluationArtifactPublication | None:
    """Caller holds the business task/evaluation lock; commit with result writes."""
    db.flush()
    rows = db.scalars(
        select(EvaluationResult)
        .where(EvaluationResult.evaluation_id == evaluation.id)
        .order_by(EvaluationResult.strategy_name, EvaluationResult.problem_id, EvaluationResult.id)
    ).all()
    if not rows:
        return None
    results: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        results.setdefault(row.strategy_name, []).append(
            {
                "problem_id": row.problem_id,
                "strategy": row.strategy_name,
                "status": row.status,
                "metrics": row.metrics,
                "error_message": row.error_message,
                "execution": row.execution_payload,
            }
        )
    expected = len(evaluation.problem_ids) * len(evaluation.strategy_names)
    payload = redact_sensitive_data(
        {
            "schema_version": 1,
            "evaluation_id": evaluation.id,
            "run_id": evaluation.run_id,
            "state": evaluation.status,
            "complete": evaluation.status == "completed" and len(rows) == expected,
            "expected_units": expected,
            "recorded_units": len(rows),
            "execution_payload_available": all(row.execution_payload is not None for row in rows),
            "results": results,
        }
    )
    task = db.get(AsyncTask, evaluation.async_task_id) if evaluation.async_task_id else None
    generation = task.celery_task_id if task else None
    digest = hashlib.sha256(
        json.dumps(
            [payload, evaluation.async_task_id, generation],
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    publication = db.get(EvaluationArtifactPublication, evaluation.id)
    if publication is not None and publication.digest == digest:
        return publication
    if publication is None:
        publication = EvaluationArtifactPublication(
            evaluation_id=evaluation.id, user_id=evaluation.user_id, revision=1, attempts=0
        )
        db.add(publication)
    else:
        publication.revision += 1
    publication.content_digest = hashlib.sha256(
        json.dumps(
            payload["results"],
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    publication.digest = digest
    publication.snapshot = {**payload, "revision": publication.revision}
    publication.source_task_id = evaluation.async_task_id
    publication.source_generation = generation
    publication.status = "pending"
    publication.error_code = None
    publication.updated_at = utcnow()
    db.flush()
    return publication


def _source_current(
    db: Session, evaluation: Evaluation, publication: EvaluationArtifactPublication
) -> bool:
    task = db.get(AsyncTask, evaluation.async_task_id) if evaluation.async_task_id else None
    return (
        publication.source_task_id == evaluation.async_task_id
        and publication.source_generation == (task.celery_task_id if task else None)
        and publication.snapshot["state"] == evaluation.status
    )


def _deleted(registry: dict[str, Any], revision: int, content_digest: str) -> bool:
    deleted = registry["deleted_revision"]
    return bool(
        (deleted is not None and deleted >= revision)
        or registry["deleted_content_digest"] == content_digest
    )


class EvaluationArtifactService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        files: FileService,
        enqueue: Callable[..., Any] | None = None,
    ):
        self._session = session_factory
        self.files = files
        self._enqueue = enqueue or self._send

    @staticmethod
    def _send(evaluation_id: str, owner: str, revision: int, manual: bool) -> Any:
        from src.celery_app import celery_app

        # Independent artifacts keep their status in SQL. Do not subscribe the
        # producer to a result backend or retry an unavailable broker indefinitely.
        options = {
            **celery_app.conf.broker_transport_options,
            "max_retries": 0,
            "socket_timeout": 2,
            "socket_connect_timeout": 2,
            "retry_on_timeout": False,
        }
        with celery_app.connection_for_write(
            connect_timeout=2, transport_options=options
        ) as connection:
            return celery_app.send_task(
                "src.tasks.artifacts.publish_evaluation_artifacts",
                args=(evaluation_id, owner, revision, manual),
                queue="default",
                retry=False,
                ignore_result=True,
                connection=connection,
            )

    def _active_snapshot(
        self, publication: EvaluationArtifactPublication, owner: str
    ) -> dict[str, Any]:
        registry = self.files.store.publication(publication.evaluation_id, owner)
        if _deleted(registry, publication.revision, publication.content_digest):
            raise HTTPException(409, "Artifact deleted")
        digest = hashlib.sha256(json_bytes(publication.snapshot)).hexdigest()
        if (
            registry["result_revision"] != publication.revision
            or registry["result_digest"] != digest
            or not registry["result_file_id"]
        ):
            raise HTTPException(409, "Current artifact is not available")
        _, data = self.files.read_file(registry["result_file_id"], owner)
        if hashlib.sha256(data).hexdigest() != digest:
            raise HTTPException(409, "Artifact integrity mismatch")
        return cast(dict[str, Any], json.loads(data))

    def state(self, evaluation_id: str, owner: str) -> dict[str, Any]:
        with self._session() as db:
            evaluation = _owned(db, evaluation_id, owner)
            publication = db.get(EvaluationArtifactPublication, evaluation_id)
            if publication is None:
                count = db.query(EvaluationResult).filter_by(evaluation_id=evaluation_id).count()
                return {
                    "revision": 0,
                    "published_revision": None,
                    "status": "unavailable",
                    "available": False,
                    "complete": False,
                    "recorded_units": count,
                    "expected_units": len(evaluation.problem_ids) * len(evaluation.strategy_names),
                    "attempts": 0,
                    "error_code": "not_published" if count else "no_results",
                    "retryable": bool(count),
                    "updated_at": None,
                }
            current = _source_current(db, evaluation, publication)
            result = {
                "revision": publication.revision,
                "published_revision": publication.published_revision,
                "status": publication.status,
                "available": False,
                "complete": publication.snapshot["complete"],
                "recorded_units": publication.snapshot["recorded_units"],
                "expected_units": publication.snapshot["expected_units"],
                "attempts": publication.attempts,
                "error_code": publication.error_code,
                "retryable": True,
                "updated_at": publication.updated_at.isoformat() + "Z",
            }
        registry = self.files.store.publication(evaluation_id, owner)
        if _deleted(registry, result["revision"], publication.content_digest):
            return {**result, "error_code": "artifact_deleted", "retryable": False}
        if not current:
            return {**result, "error_code": "source_superseded", "retryable": True}
        if registry["result_revision"] == result["revision"] and registry["result_file_id"]:
            try:
                _, data = self.files.read_file(registry["result_file_id"], owner)
                if hashlib.sha256(data).hexdigest() != registry["result_digest"]:
                    raise HTTPException(409, "Artifact integrity mismatch")
            except (HTTPException, OSError):
                result["error_code"] = "artifact_unavailable"
            else:
                result["available"] = (
                    publication.status == "published"
                    and publication.published_revision == publication.revision
                )
        return result

    @staticmethod
    def _mark_published(db: Session, publication: EvaluationArtifactPublication) -> None:
        publication.status = "published"
        publication.published_revision = publication.revision
        publication.error_code = None
        publication.updated_at = utcnow()

    def _fail(self, evaluation_id: str, owner: str, revision: int, code: str) -> None:
        with self._session() as db:
            _owned(db, evaluation_id, owner, lock=True)
            publication = db.get(EvaluationArtifactPublication, evaluation_id)
            if publication is not None and publication.revision == revision:
                if publication.status == "published" and publication.published_revision == revision:
                    # A failure describes an earlier observation; never invalidate a
                    # successfully repaired/current immutable file because it arrived late.
                    try:
                        self._active_snapshot(publication, owner)
                    except (HTTPException, OSError, ValueError):
                        pass
                    else:
                        return
                publication.status = "failed"
                publication.error_code = code
                publication.updated_at = utcnow()
                db.commit()
        logger.warning(
            "artifact_publication_failed evaluation_id=%s revision=%s code=%s",
            evaluation_id,
            revision,
            code,
        )

    def publish(
        self, evaluation_id: str, owner: str, revision: int, manual: bool = False
    ) -> dict[str, Any]:
        with self._session() as db:
            evaluation = _owned(db, evaluation_id, owner, lock=True)
            publication = db.get(EvaluationArtifactPublication, evaluation_id)
            if (
                publication is None
                or publication.revision != revision
                or not _source_current(db, evaluation, publication)
            ):
                return self.state(evaluation_id, owner)
            snapshot = publication.snapshot
            content_digest = publication.content_digest
            publication.attempts += 1
            db.commit()
        digest = hashlib.sha256(json_bytes(snapshot)).hexdigest()
        candidate: str | None = None
        invalid_file_id: str | None = None
        try:
            registry = self.files.store.publication(evaluation_id, owner)
            if _deleted(registry, revision, publication.content_digest):
                raise HTTPException(409, "Artifact deleted")
            existing = None
            if (
                registry["result_revision"] == revision
                and registry["result_digest"] == digest
                and registry["result_file_id"]
            ):
                try:
                    metadata, data = self.files.read_file(registry["result_file_id"], owner)
                    if hashlib.sha256(data).hexdigest() != digest:
                        raise HTTPException(409, "Artifact integrity mismatch")
                    existing = metadata["id"]
                except (HTTPException, OSError):
                    if not manual:
                        raise HTTPException(409, "Artifact unavailable") from None
                    invalid_file_id = registry["result_file_id"]
            if existing is None:
                metadata = self.files.find_snapshot_candidate(
                    evaluation_id, owner, digest
                ) or self.files.stage_snapshot(evaluation_id, owner, snapshot)
                candidate = metadata["id"]
                # Verify immutable staged bytes before the final cross-database activation.
                _, data = self.files.read_file(candidate, owner)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise HTTPException(409, "Artifact integrity mismatch")
            with self._session() as db:
                evaluation = _owned(db, evaluation_id, owner, lock=True)
                publication = db.get(
                    EvaluationArtifactPublication, evaluation_id, populate_existing=True
                )
                if (
                    publication is None
                    or publication.revision != revision
                    or not _source_current(db, evaluation, publication)
                ):
                    return self.state(evaluation_id, owner)
                if existing is None:
                    assert candidate is not None
                    self.files.store.activate_snapshot(
                        evaluation_id,
                        owner,
                        candidate,
                        revision,
                        digest,
                        invalid_file_id,
                        content_digest,
                    )
                self._mark_published(db, publication)
                db.commit()
        except Exception as exc:
            code = "storage_error"
            if isinstance(exc, HTTPException):
                code = (
                    "storage_limit"
                    if exc.status_code == 413
                    else (
                        "artifact_deleted"
                        if exc.detail == "Artifact deleted"
                        else (
                            "artifact_unavailable"
                            if exc.detail == "Artifact unavailable"
                            else "publication_conflict"
                        )
                    )
                )
            try:
                self._fail(evaluation_id, owner, revision, code)
            except Exception:
                logger.warning(
                    "artifact_failure_record_unavailable evaluation_id=%s revision=%s",
                    evaluation_id,
                    revision,
                )
        finally:
            if candidate is not None:
                try:
                    self.files.discard_candidate(candidate, owner)
                except Exception:
                    logger.warning(
                        "artifact_candidate_cleanup_deferred evaluation_id=%s", evaluation_id
                    )
        return self.state(evaluation_id, owner)

    def retry(self, evaluation_id: str, owner: str) -> dict[str, Any]:
        with self._session() as db:
            evaluation = _owned(db, evaluation_id, owner, lock=True)
            registry = self.files.store.publication(evaluation_id, owner)
            publication = db.get(EvaluationArtifactPublication, evaluation_id)
            if publication is None and registry["deleted_revision"] is not None:
                raise HTTPException(409, "Artifact deleted")
            if publication is not None and _deleted(
                registry, publication.revision, publication.content_digest
            ):
                raise HTTPException(409, "Artifact deleted")
            publication = stage_publication(db, evaluation)
            if publication is None:
                raise HTTPException(409, "No results available for publication")
            revision = publication.revision
            if _deleted(registry, revision, publication.content_digest):
                raise HTTPException(409, "Artifact deleted")
            if not _source_current(db, evaluation, publication):
                raise HTTPException(
                    409, "Wait for the current evaluation execution to commit results"
                )
            db.commit()
        state = self.state(evaluation_id, owner)
        if state["available"]:
            return state
        ready = False
        with self._session() as db:
            evaluation = _owned(db, evaluation_id, owner, lock=True)
            publication = db.get(EvaluationArtifactPublication, evaluation_id)
            if (
                publication is None
                or publication.revision != revision
                or not _source_current(db, evaluation, publication)
            ):
                raise HTTPException(409, "Artifact revision changed; refresh publication status")
            if publication.status == "published" and publication.published_revision == revision:
                try:
                    self._active_snapshot(publication, owner)
                except (HTTPException, OSError, ValueError):
                    pass
                else:
                    ready = True
            if not ready:
                publication.status = "pending"
                publication.error_code = None
            db.commit()
        if ready:
            return self.state(evaluation_id, owner)
        try:
            self._enqueue(evaluation_id, owner, revision, True)
        except Exception:
            self._fail(evaluation_id, owner, revision, "queue_unavailable")
            current = self.state(evaluation_id, owner)
            if current["available"]:
                return current
            raise HTTPException(503, "Artifact publication could not be queued") from None
        return self.state(evaluation_id, owner)

    def enqueue_retry(self, evaluation_id: str, owner: str, revision: int) -> None:
        try:
            self._enqueue(evaluation_id, owner, revision, False)
        except Exception:
            self._fail(evaluation_id, owner, revision, "queue_unavailable")

    def export_results(
        self, evaluation_id: str, owner: str, format_name: str
    ) -> tuple[tuple[str, str, bytes], dict[str, str]]:
        with self._session() as db:
            publication = db.get(EvaluationArtifactPublication, evaluation_id)
            if publication is None:
                return self.files.export_results(evaluation_id, owner, format_name), {}
            evaluation = _owned(db, evaluation_id, owner)
            if (
                publication.status != "published"
                or publication.published_revision != publication.revision
                or not _source_current(db, evaluation, publication)
            ):
                raise HTTPException(
                    409, "Current result artifact is not available; check publication status"
                )
            revision, digest = publication.revision, publication.digest
        # Read and verify one immutable file, rather than reading the current pointer
        # again after producing the response headers.
        payload = self._active_snapshot(publication, owner)
        with self._session() as db:
            evaluation = _owned(db, evaluation_id, owner, lock=True)
            current = db.get(EvaluationArtifactPublication, evaluation_id, populate_existing=True)
            registry = self.files.store.publication(evaluation_id, owner)
            if (
                current is None
                or current.revision != revision
                or current.digest != digest
                or current.status != "published"
                or current.published_revision != revision
                or not _source_current(db, evaluation, current)
                or _deleted(registry, revision, current.content_digest)
                or registry["result_revision"] != revision
            ):
                raise HTTPException(409, "Artifact revision changed; refresh publication status")
        headers = {
            "X-Artifact-Revision": str(payload["revision"]),
            "X-Artifact-Completeness": "complete" if payload["complete"] else "partial",
        }
        return self.files.export_payload(payload, owner, format_name), headers
