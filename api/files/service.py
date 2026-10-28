"""Private artifacts, batch import, export and cleanup with no public path input."""

import csv
import hashlib
import html
import io
import json
import logging
import os
import tempfile
import threading
import time
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO, cast

import yaml
from fastapi import HTTPException
from pydantic import ValidationError

from api.auth.service import AuthService
from api.files.config import FileSettings
from api.files.parsing import (
    bad,
    filename_suffix,
    normalize_config,
    parse_file,
    problem_error,
    transform_validated,
    validate_problem,
)
from api.files.store import FileStore
from src.checkpoints import write_checkpoint
from src.models import ExecutionResult, Problem
from src.reporting.chart_generator import ChartGenerator
from src.reporting.csv_exporter import CSVExporter
from src.utils.secrets import redact_sensitive_data

logger = logging.getLogger(__name__)
_CHART_LOCK = threading.Lock()
PUBLIC_FIELDS = (
    "id",
    "filename",
    "suffix",
    "category",
    "size",
    "sha256",
    "created_at",
    "expires_at",
    "run_id",
)


def json_bytes(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def safe_cell(value: str) -> str:
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r"))
        else value
    )


class FileService:
    def __init__(self, auth: AuthService, settings: FileSettings):
        self.auth = auth
        self.settings = settings
        self.transfers = threading.BoundedSemaphore(settings.FILE_MAX_CONCURRENT_TRANSFERS)
        self.imports = threading.BoundedSemaphore(settings.FILE_MAX_CONCURRENT_IMPORTS)
        self.store = FileStore(auth.store)
        self.root = settings.UPLOAD_DIR.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, relative: str, user_id: str) -> Path:
        candidate = self.root / relative
        owner = self.root / "users" / user_id
        if not candidate.is_relative_to(owner):
            raise HTTPException(404, "File not found")
        # Immutable generated paths should never contain symlinks, even when a
        # link happens to resolve within the upload root.
        current = candidate
        while current != self.root:
            if current.is_symlink():
                raise HTTPException(404, "File not found")
            current = current.parent
        if not candidate.resolve().is_relative_to(owner.resolve()):
            raise HTTPException(404, "File not found")
        return candidate

    @staticmethod
    def metadata(record: dict[str, Any]) -> dict[str, Any]:
        return {key: record[key] for key in PUBLIC_FIELDS}

    def _temporary(self, user_id: str) -> Any:
        relative = f"users/{user_id}/temp"
        directory = self.path(relative, user_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return tempfile.NamedTemporaryFile(
            mode="wb", suffix=".part", prefix="stage-", dir=directory, delete=False
        )

    def _persist(
        self,
        user_id: str,
        data: bytes,
        suffix: str,
        filename: str,
        category: str,
        run_id: str | None = None,
        temporary: bool = False,
    ) -> dict[str, Any]:
        if len(data) > self.settings.FILE_UPLOAD_MAX_BYTES:
            raise HTTPException(413, "File exceeds size limit")
        file_id = str(uuid.uuid4())
        directory = "temp" if temporary or category == "upload" else category
        relative = f"users/{user_id}/{directory}/{file_id}{suffix}"
        target = self.path(relative, user_id)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        stage = self._temporary(user_id)
        try:
            with stage:
                stage.write(data)
                stage.flush()
                os.fsync(stage.fileno())
            os.replace(stage.name, target)
            now = int(time.time())
            record = {
                "id": file_id,
                "user_id": user_id,
                "filename": filename,
                "relative_path": relative,
                "suffix": suffix,
                "category": category,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "created_at": now,
                "expires_at": (
                    now + self.settings.FILE_TTL_SECONDS
                    if temporary or category == "upload"
                    else None
                ),
                "run_id": run_id,
            }
            self.store.add_file(record, self.settings.FILE_MAX_USER_BYTES)
            self.auth.audit("file_store", user_id, file_id)
            return self.metadata(record)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            Path(stage.name).unlink(missing_ok=True)

    def upload(
        self,
        source: BinaryIO,
        filename: str | None,
        content_type: str | None,
        user_id: str,
        config_kind: str | None = None,
    ) -> dict[str, Any]:
        suffix = filename_suffix(filename, content_type)
        if config_kind and suffix not in {".json", ".yaml", ".yml"}:
            raise bad("Configuration files must be JSON or YAML")
        maximum = (
            min(self.settings.FILE_CONFIG_MAX_BYTES, self.settings.FILE_UPLOAD_MAX_BYTES)
            if config_kind
            else self.settings.FILE_UPLOAD_MAX_BYTES
        )
        stage = self._temporary(user_id)
        try:
            size = 0
            with stage:
                while chunk := source.read(65536):
                    size += len(chunk)
                    if size > maximum:
                        raise HTTPException(413, "File exceeds size limit")
                    stage.write(chunk)
            data = parse_file(Path(stage.name), suffix, self.settings.FILE_IMPORT_MAX_ITEMS)
            if config_kind:
                normalized = normalize_config(data, config_kind)
                encoded = (
                    yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False).encode("utf-8")
                    if suffix in {".yaml", ".yml"}
                    else json_bytes(normalized)
                )
                record = self._persist(
                    user_id, encoded, suffix, filename or "config.json", "configs"
                )
                return {
                    "file": record,
                    "config_type": config_kind,
                    "config": normalized,
                    "credentials_removed": True,
                }
            if isinstance(data, dict) and ("llm_config" in data or "models" in data):
                raise bad("Use configs/upload for evaluation configuration files")
            encoded = Path(stage.name).read_bytes()
            return {
                "file": self._persist(
                    user_id, encoded, suffix, filename or "upload.json", "upload"
                ),
                "parsed": True,
            }
        finally:
            stage.close()
            Path(stage.name).unlink(missing_ok=True)

    def read_file(self, file_id: str, user_id: str) -> tuple[dict[str, Any], bytes]:
        record = self.store.owned_file(file_id, user_id)
        path = self.path(record["relative_path"], user_id)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise HTTPException(404, "File not found") from None
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise HTTPException(409, "Stored file integrity check failed")
        return self.metadata(record), data

    def process_job(
        self,
        job_id: str,
        user_id: str,
        should_pause: Callable[[], bool] | None = None,
        claimed: bool = False,
    ) -> None:
        with self.imports:
            self._process_job(job_id, user_id, should_pause=should_pause, claimed=claimed)

    def _process_job(
        self,
        job_id: str,
        user_id: str,
        should_pause: Callable[[], bool] | None = None,
        claimed: bool = False,
    ) -> None:
        if not claimed and not self.store.claim_job(job_id, user_id):
            return
        try:
            job = self.store.job(job_id, user_id)
            record = self.store.owned_file(job["file_id"], user_id, allow_expired=True)
            path = self.path(record["relative_path"], user_id)
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise bad("Stored upload integrity check failed")
            data = parse_file(path, record["suffix"], self.settings.FILE_IMPORT_MAX_ITEMS)
            if not isinstance(data, list) or not data:
                raise bad("Dataset must be a non-empty array")
            if len(data) > self.settings.FILE_IMPORT_MAX_ITEMS:
                raise HTTPException(413, "Too many problems")
            checkpoint_path = self.path(
                f"users/{user_id}/imports/{job_id}.checkpoint.json", user_id
            )
            saved = (
                json.loads(checkpoint_path.read_text(encoding="utf-8"))
                if checkpoint_path.exists()
                else {}
            )
            if saved and saved.get("sha256") != record["sha256"]:
                raise bad("Import checkpoint inputs changed")
            problems = [Problem.model_validate(value) for value in saved.get("problems", [])]
            errors: list[dict[str, Any]] = saved.get("errors", [])
            processed = int(saved.get("processed", 0))

            def checkpoint() -> None:
                write_checkpoint(
                    checkpoint_path,
                    {
                        "sha256": record["sha256"],
                        "processed": processed,
                        "problems": [p.model_dump(mode="json") for p in problems],
                        "errors": errors,
                    },
                )
                self.store.progress(job_id, processed, len(data))

            self.store.progress(job_id, processed, len(data))
            for index in range(processed, len(data)):
                item = data[index]
                if should_pause is not None and should_pause():
                    checkpoint()
                    self.store.pause_job(job_id)
                    return
                try:
                    problems.append(validate_problem(item, record["suffix"] == ".csv"))
                except (ValueError, TypeError, ValidationError) as error:
                    # Store only field/type diagnostics, never raw record values.
                    if len(errors) < 200:
                        errors.append(problem_error(index, error))
                processed = index + 1
                if (index + 1) % 100 == 0 or index + 1 == len(data):
                    checkpoint()
            if should_pause is not None and should_pause():
                checkpoint()
                self.store.pause_job(job_id)
                return
            report = {
                "total": len(data),
                "valid": len(problems),
                "invalid": len(data) - len(problems),
                "errors": errors,
                "errors_truncated": len(data) - len(problems) > len(errors),
                "file_id": record["id"],
            }
            if not problems:
                raise bad("All problems failed schema validation", report)
            transformed = transform_validated(problems)
            self.store.merge_dataset(
                job_id,
                user_id,
                [p.model_dump(mode="json") for p in transformed],
                report,
                self.settings.FILE_UPLOAD_MAX_BYTES,
                self.settings.FILE_IMPORT_MAX_ITEMS,
            )
            self.auth.audit("dataset_import", user_id, job_id)
        except HTTPException as error:
            self.store.fail_job(job_id, {"status_code": error.status_code, "detail": error.detail})
        except Exception:
            # A parser/storage exception may contain uploaded secrets/paths.
            self.store.fail_job(job_id, {"status_code": 500, "detail": "Import failed"})
            logger.warning("file_import_failed job_id=%s", job_id)

    def export_dataset(self, user_id: str, format_name: str) -> tuple[str, str, bytes]:
        data = self.store.dataset(user_id)
        if format_name == "json":
            return "problems.json", "application/json", json_bytes(data)
        if format_name != "csv":
            raise bad("Dataset format must be json or csv")
        stream = io.StringIO(newline="")
        # Every schema field is preserved, including nullable values and
        # non-default judge/entry/source metadata. JSON cells are also safe in
        # spreadsheets: a string cell begins with a quote, never a formula.
        fields = list(Problem.model_fields)
        writer = csv.DictWriter(stream, fieldnames=[*fields, "_harness_csv_encoding"])
        writer.writeheader()
        for problem in data:
            row = {
                key: json.dumps(problem.get(key), ensure_ascii=False, allow_nan=False)
                for key in fields
            }
            row["_harness_csv_encoding"] = "json-v1"
            writer.writerow(row)
        return "problems.csv", "text/csv", stream.getvalue().encode("utf-8-sig")

    def publish_results(
        self, run_id: str, user_id: str, results: dict[str, list[ExecutionResult]]
    ) -> dict[str, Any]:
        """Trusted #149 worker hook, using the API task's registered owner/ID.

        No HTTP endpoint accepts an owner claim or a server filesystem path.
        """
        with self.store.connection() as db:
            self.store.check_run(db, run_id, user_id)
        canonical = {}
        count = 0
        for strategy, items in results.items():
            canonical[strategy] = [
                ExecutionResult.model_validate(item).model_dump(mode="json") for item in items
            ]
            count += len(items)
        if count > self.settings.FILE_IMPORT_MAX_ITEMS:
            raise ValueError("Too many result records")
        payload = json_bytes(redact_sensitive_data(canonical))
        metadata = self._persist(
            user_id, payload, ".json", "results.json", "results", run_id=run_id
        )
        self.store.activate_result(run_id, user_id, metadata["id"])
        self.cleanup()
        return metadata

    def _result_payload(self, run_id: str, user_id: str) -> dict[str, Any]:
        record = self.store.result_file(run_id, user_id)
        _, data = self.read_file(record["id"], user_id)
        return cast(dict[str, Any], json.loads(data))

    def _render_results(
        self, payload: dict[str, Any], format_name: str, user_id: str
    ) -> tuple[str, str, bytes]:
        if format_name == "json":
            return "results.json", "application/json", json_bytes(payload)
        text = json_bytes(payload).decode("utf-8")
        if format_name in {"md", "markdown"}:
            # A JSON code block cannot be escaped by untrusted triple backticks.
            text = text.replace("`", "\\u0060")
            return (
                "report.md",
                "text/markdown",
                ("# Evaluation results\n\n```json\n" + text + "```\n").encode("utf-8"),
            )
        if format_name == "html":
            return (
                "report.html",
                "text/html",
                (
                    "<!doctype html><meta charset='utf-8'><title>Evaluation results</title><h1>Evaluation results</h1><pre>"
                    + html.escape(text)
                    + "</pre>"
                ).encode("utf-8"),
            )
        if format_name == "csv":
            models = {
                strategy: [ExecutionResult.model_validate(item) for item in items]
                for strategy, items in payload.items()
            }
            temporary = self._temporary(user_id)
            temporary.close()
            path = Path(temporary.name)
            try:
                CSVExporter.export_all(models, str(path))
                csv.field_size_limit(
                    max(csv.field_size_limit(), self.settings.FILE_UPLOAD_MAX_BYTES)
                )
                with path.open(encoding="utf-8-sig", newline="") as f:
                    rows = list(csv.reader(f))
                stream = io.StringIO(newline="")
                writer = csv.writer(stream)
                writer.writerows([[safe_cell(value) for value in row] for row in rows])
                return "results.csv", "text/csv", stream.getvalue().encode("utf-8-sig")
            finally:
                path.unlink(missing_ok=True)
        if format_name == "png":
            metrics = {}
            for strategy, items in payload.items():
                solved = sum(ExecutionResult.model_validate(item).is_successful() for item in items)
                metrics[strategy] = {
                    "success_rate": solved / len(items) if items else 0,
                    "solved_problems": solved,
                    "total_problems": len(items),
                }
            with _CHART_LOCK:
                chart = ChartGenerator.generate_success_rate_chart(metrics)
            if chart is None:
                raise HTTPException(404, "Chart not available")
            try:
                return "success-rate.png", "image/png", chart.getvalue()
            finally:
                chart.close()
        if format_name == "zip":
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for kind in ["json", "csv", "md", "html", "png"]:
                    try:
                        name, _, data = self._render_results(payload, kind, user_id)
                    except HTTPException as error:
                        if kind == "png" and error.status_code == 404:
                            continue
                        raise
                    bundle.writestr(name, data)
            return "results.zip", "application/zip", archive.getvalue()
        raise bad("Result format must be json, csv, markdown, html, png or zip")

    def export_results(self, run_id: str, user_id: str, format_name: str) -> tuple[str, str, bytes]:
        payload = self._result_payload(run_id, user_id)
        result = self._render_results(payload, format_name, user_id)
        if len(result[2]) > self.settings.FILE_UPLOAD_MAX_BYTES:
            raise HTTPException(413, "Export exceeds size limit")
        return result

    def delete_file(self, file_id: str, user_id: str) -> None:
        self.store.owned_file(file_id, user_id)
        self.store.mark_file_deleted(file_id, user_id)
        self.cleanup()
        self.auth.audit("file_delete", user_id, file_id)

    def delete_run(self, run_id: str, user_id: str) -> None:
        self.store.mark_run_deleted(run_id, user_id)
        self.cleanup()

    def cleanup(self) -> int:
        now, removed = int(time.time()), 0
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE api_file_jobs SET status='failed',result=?,updated_at=? WHERE status IN ('pending','running') AND updated_at<=?",
                (
                    json.dumps({"status_code": 409, "detail": "Import interrupted or timed out"}),
                    now,
                    now - self.settings.FILE_IMPORT_TIMEOUT_SECONDS,
                ),
            )
            records = db.execute(
                "SELECT * FROM api_file_objects f WHERE (f.deleted=1 OR f.expires_at<=? OR EXISTS(SELECT 1 FROM api_file_runs r WHERE r.run_id=f.run_id AND r.deleted=1)) AND NOT EXISTS(SELECT 1 FROM api_file_jobs j WHERE j.file_id=f.id AND j.status IN ('pending','running'))",
                (now,),
            ).fetchall()
            for record in records:
                try:
                    self.path(record["relative_path"], record["user_id"]).unlink(missing_ok=True)
                except (OSError, HTTPException):
                    logger.warning("file_cleanup_retry file_id=%s", record["id"])
                    continue
                db.execute("DELETE FROM api_file_objects WHERE id=?", (record["id"],))
                removed += 1
        # Reclaim interrupted staging and the rename-before-metadata crash
        # window. Only service-generated names in private category directories
        # qualify; a registered object is never removed by this pass.
        grace = max(3600, self.settings.FILE_TTL_SECONDS)
        for staging in self.root.glob("users/*/*/*"):
            try:
                relative = staging.relative_to(self.root)
                if len(relative.parts) != 4 or relative.parts[2] not in {
                    "temp",
                    "configs",
                    "results",
                    "datasets",
                }:
                    continue
                if staging.name.startswith("stage-") and staging.suffix == ".part":
                    generated = True
                else:
                    try:
                        generated = str(
                            uuid.UUID(staging.stem)
                        ) == staging.stem and staging.suffix in {
                            ".json",
                            ".yaml",
                            ".yml",
                            ".csv",
                            ".png",
                            ".zip",
                        }
                    except ValueError:
                        generated = False
                if not generated:
                    continue
                candidate = self.path(relative.as_posix(), relative.parts[1])
                if not candidate.is_file() or candidate.stat().st_mtime >= now - grace:
                    continue
                with self.store.connection() as db:
                    if db.execute(
                        "SELECT 1 FROM api_file_objects WHERE relative_path=?",
                        (relative.as_posix(),),
                    ).fetchone():
                        continue
                candidate.unlink(missing_ok=True)
                removed += 1
            except (OSError, HTTPException):
                logger.warning("file_orphan_cleanup_retry")
        return removed
