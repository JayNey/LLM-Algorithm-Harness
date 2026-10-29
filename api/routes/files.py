"""Owner-scoped upload, import progress and download endpoints."""

from collections.abc import AsyncIterator
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, UploadFile

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.db.engine import get_db
from api.files.dependencies import file_service
from api.files.service import FileService
from api.files.templates import TEMPLATES, template
from api.schemas import ApiResponse
from src.task_manager import TaskManager

router = APIRouter(prefix="/api/v1", tags=["files"])
UPLOAD_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "mode": {
                            "type": "string",
                            "enum": ["append", "overwrite"],
                            "default": "append",
                        },
                        "validate": {"type": "boolean", "default": True},
                        "config_type": {"type": "string", "enum": ["harness", "experiment"]},
                    },
                }
            }
        },
    }
}


async def upload_form(request: Request) -> AsyncIterator[FormData]:
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise HTTPException(415, "Multipart form data required")
    async with request.form(max_files=1, max_fields=5, max_part_size=65536) as form:
        files = [value for _, value in form.multi_items() if isinstance(value, UploadFile)]
        if len(files) != 1 or not isinstance(form.get("file"), UploadFile):
            raise HTTPException(400, "Exactly one file field is required")
        yield form


def uploaded(form: FormData) -> UploadFile:
    value = form["file"]
    if not isinstance(value, UploadFile):
        raise HTTPException(400, "File required")
    return value


def download(name: str, media_type: str, data: bytes) -> Response:
    return Response(
        data,
        media_type=media_type,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'",
            "Cache-Control": "no-store",
        },
    )


@router.post("/files/upload", status_code=201, openapi_extra=UPLOAD_SCHEMA)
async def upload_file(
    form: FormData = Depends(upload_form),
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> ApiResponse[dict[str, Any]]:
    file = uploaded(form)
    result = await run_in_threadpool(
        service.upload, file.file, file.filename, file.content_type, principal.user_id
    )
    return ApiResponse(success=True, data=result, message="File uploaded")


@router.post("/problems/upload", openapi_extra=UPLOAD_SCHEMA)
async def upload_problems(
    form: FormData = Depends(upload_form),
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> ApiResponse[dict[str, Any]]:
    mode = str(form.get("mode", "append"))
    if mode not in {"append", "overwrite"}:
        raise HTTPException(400, "Mode must be append or overwrite")
    if str(form.get("validate", "true")).lower() not in {"true", "1"}:
        raise HTTPException(400, "Schema validation is required")
    file = uploaded(form)
    result = await run_in_threadpool(
        service.upload, file.file, file.filename, file.content_type, principal.user_id
    )
    file_id = result["file"]["id"]
    try:
        job_id = service.store.create_job(
            file_id, principal.user_id, mode, service.settings.FILE_MAX_ACTIVE_IMPORTS
        )
        await run_in_threadpool(service.process_job, job_id, principal.user_id)
        job = service.store.job(job_id, principal.user_id)
        if job["status"] != "completed":
            failure = job["result"] or {"status_code": 500, "detail": "Import failed"}
            raise HTTPException(failure["status_code"], failure["detail"])
        return ApiResponse(
            success=True,
            data={"file_id": file_id, "job_id": job_id, "validation": job["result"]},
            message="Problems imported",
        )
    except Exception:
        # Failed direct imports should not leave unnecessary raw uploads.
        try:
            service.delete_file(file_id, principal.user_id)
        except HTTPException:
            pass
        raise


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(min_length=1, max_length=64)
    mode: Literal["append", "overwrite"] = "append"


@router.post("/problems/import", status_code=202)
def import_uploaded(
    request: ImportRequest,
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
    db: Session = Depends(get_db),
) -> ApiResponse[dict[str, Any]]:
    job_id = service.store.create_job(
        request.file_id, principal.user_id, request.mode, service.settings.FILE_MAX_ACTIVE_IMPORTS
    )
    task = TaskManager(db, file_store=service.store).enqueue_task(
        task_type="import",
        entity_id=job_id,
        user_id=principal.user_id,
        celery_task_name="src.tasks.imports.run_import_task",
        celery_task_args=(job_id, principal.user_id),
    )
    return ApiResponse(
        success=True,
        data={"job_id": job_id, "task_id": task.id, "status": "pending"},
        message="Import queued",
    )


@router.get("/imports/{job_id}")
def import_progress(
    job_id: str,
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> ApiResponse[dict[str, Any]]:
    job = service.store.job(job_id, principal.user_id)
    total, processed = job["total"], job["processed"]
    data = {
        "job_id": job_id,
        "status": job["status"],
        "processed": processed,
        "total": total,
        "percentage": (
            100 if job["status"] == "completed" else (processed / total * 100 if total else 0)
        ),
        "result": job["result"],
    }
    return ApiResponse(success=True, data=data, message="Import progress")


@router.post("/configs/upload", status_code=201, openapi_extra=UPLOAD_SCHEMA)
async def upload_config(
    form: FormData = Depends(upload_form),
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> ApiResponse[dict[str, Any]]:
    file = uploaded(form)
    result = await run_in_threadpool(
        service.upload,
        file.file,
        file.filename,
        file.content_type,
        principal.user_id,
        str(form.get("config_type", "harness")),
    )
    return ApiResponse(success=True, data=result, message="Configuration validated and stored")


@router.get("/configs/templates")
def templates(principal: Principal = Depends(current_user)) -> ApiResponse[list[dict[str, str]]]:
    return ApiResponse(
        success=True,
        data=[{"name": name, "type": value["type"]} for name, value in TEMPLATES.items()],
        message="Configuration templates",
    )


@router.get("/configs/templates/{name}")
def get_template(
    name: str, principal: Principal = Depends(current_user)
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(success=True, data=template(name), message="Configuration template")


@router.get("/files/{file_id}")
def file_metadata(
    file_id: str,
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(
        success=True,
        data=service.metadata(service.store.owned_file(file_id, principal.user_id)),
        message="File metadata",
    )


@router.get("/files/{file_id}/download")
def download_file(
    file_id: str,
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> Response:
    metadata, data = service.read_file(file_id, principal.user_id)
    media_type = {
        ".json": "application/json",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
        ".csv": "text/csv",
        ".png": "image/png",
        ".zip": "application/zip",
    }.get(metadata["suffix"], "application/octet-stream")
    return download(metadata["filename"], media_type, data)


@router.delete("/files/{file_id}", status_code=204)
def delete_file(
    file_id: str,
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> Response:
    service.delete_file(file_id, principal.user_id)
    return Response(status_code=204)


@router.get("/problems/export")
def export_problems(
    format: str = "json",
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> Response:
    return download(*service.export_dataset(principal.user_id, format))


@router.get("/results/{run_id}/download")
@router.get("/results/{run_id}/export")
def download_results(
    run_id: str,
    format: str = "json",
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> Response:
    return download(*service.export_results(run_id, principal.user_id, format))


@router.get("/results/{run_id}/charts/{chart_name}")
def download_chart(
    run_id: str,
    chart_name: str,
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> Response:
    if chart_name != "success-rate":
        raise HTTPException(404, "Chart not found")
    return download(*service.export_results(run_id, principal.user_id, "png"))


@router.get("/datasets")
def datasets(
    principal: Principal = Depends(current_user),
    service: FileService = Depends(file_service),
) -> ApiResponse[list[dict[str, Any]]]:
    try:
        data = service.datasets(principal.user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return ApiResponse(success=True, data=data, message="Datasets retrieved")
