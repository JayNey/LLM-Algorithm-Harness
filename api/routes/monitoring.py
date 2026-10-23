"""Protected monitoring foundations and owner-scoped task logs/quotas."""

import math
import time
from collections.abc import Iterator
from datetime import datetime
from tempfile import SpooledTemporaryFile
from typing import Any, BinaryIO, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.monitoring.capabilities import evaluation_capability
from api.monitoring.dependencies import administrator, monitor_service
from api.monitoring.service import MonitorService
from api.schemas import ApiResponse

router = APIRouter(prefix="/api/v1", tags=["monitoring"])


class LogDownloadResponse(StreamingResponse):
    """Close the private temporary file even if the client disconnects."""

    def __init__(self, stream: BinaryIO, headers: dict[str, str]):
        self.log_stream = stream

        def chunks() -> Iterator[bytes]:
            while chunk := stream.read(65536):
                yield chunk

        super().__init__(chunks(), media_type="text/plain", headers=headers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.log_stream.close()


def answer(data: Any) -> ApiResponse[Any]:
    return ApiResponse(success=True, data=data, message="Monitoring data")


def epoch(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(400, "Log times require a timezone")
    result = value.timestamp()
    if not math.isfinite(result) or result < 0:
        raise HTTPException(400, "Log times must be at or after the Unix epoch")
    return result


def log_filters(
    level: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    search: str | None = Query(None, max_length=200),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0, le=100000),
) -> dict[str, Any]:
    if level is not None and level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise HTTPException(400, "Unknown log level")
    first, last = epoch(start), epoch(end)
    if first is not None and last is not None and first > last:
        raise HTTPException(400, "Log start must precede end")
    return {
        "level": level.upper() if level else None,
        "start": first,
        "end": last,
        "search": search,
        "limit": limit,
        "offset": offset,
    }


@router.get("/system/health")
def detailed_health(
    include_sandbox: bool = False,
    admin: Principal = Depends(administrator),
    monitor: MonitorService = Depends(monitor_service),
) -> ApiResponse[Any]:
    return answer(monitor.health(include_sandbox))


@router.get("/health/database")
def database_health(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.probes.database())


@router.get("/health/redis")
def redis_health(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.probes.redis())


@router.get("/health/workers")
@router.get("/system/workers")
def worker_health(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.probes.workers())


@router.get("/health/sandbox")
def sandbox_health(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.probes.sandbox())


@router.get("/system/resources")
def resources(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.probes.resources())


@router.get("/system/status")
def system_status(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    snapshot = monitor.task_snapshot()
    async_snapshot = monitor.task_snapshot(task_source="async_task")
    health = monitor.health()
    redis_observation = health["checks"].get("redis", {})
    return answer(
        {
            "uptime_seconds": round(time.monotonic() - monitor.started, 3),
            "scope": "current_api_process",
            "task_counts": snapshot["counts"],
            "task_count": snapshot["total"],
            "task_status": snapshot["status"],
            "task_source": snapshot["source"],
            "async_task_counts": async_snapshot["counts"],
            "async_task_count": async_snapshot["total"],
            "async_task_status": async_snapshot["status"],
            "async_task_source": async_snapshot["source"],
            **evaluation_capability(),
            "health": health,
            "resources": monitor.probes.resources(),
            "workers": health["checks"]["workers"],
            "queue_metrics": {
                "broker_queue": {
                    **redis_observation.get(
                        "broker_queue",
                        {
                            "status": "unknown",
                            "waiting": None,
                            "queues": None,
                        },
                    ),
                    "source": "redis_broker",
                    "scope": "configured_business_queues",
                    "cached": redis_observation.get("cached", False),
                    "age_seconds": redis_observation.get("age_seconds"),
                },
                "database_pending": {
                    "status": async_snapshot["status"],
                    "source": async_snapshot["source"],
                    "count": (
                        async_snapshot["counts"].get("pending", 0)
                        if async_snapshot["status"] == "ok"
                        else None
                    ),
                },
                "worker_reserved": {
                    "status": health["checks"]["workers"]["status"],
                    "source": "responding_celery_workers",
                    "count": health["checks"]["workers"].get("reserved"),
                    "cluster_complete": False,
                    "cached": health["checks"]["workers"].get("cached", False),
                    "age_seconds": health["checks"]["workers"].get("age_seconds"),
                },
            },
            "containers": monitor.probes.containers(),
        }
    )


@router.get("/system/tasks/running")
def running_tasks(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0, le=100000),
    task_source: Literal["legacy_evaluation", "async_task"] = "legacy_evaluation",
    admin: Principal = Depends(administrator),
    monitor: MonitorService = Depends(monitor_service),
) -> ApiResponse[Any]:
    return answer(monitor.task_snapshot("running", limit, offset, task_source))


@router.get("/system/tasks/queued")
def queued_tasks(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0, le=100000),
    task_source: Literal["legacy_evaluation", "async_task"] = "legacy_evaluation",
    admin: Principal = Depends(administrator),
    monitor: MonitorService = Depends(monitor_service),
) -> ApiResponse[Any]:
    return answer(monitor.task_snapshot("pending", limit, offset, task_source))


@router.get("/metrics/api-stats")
def api_stats(
    window_seconds: int = Query(60, ge=1, le=86400),
    admin: Principal = Depends(administrator),
    monitor: MonitorService = Depends(monitor_service),
) -> ApiResponse[Any]:
    return answer(monitor.store.api_stats(window_seconds))


@router.get("/metrics/performance")
def performance(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.performance())


@router.get("/metrics/llm-stats")
def llm_stats(
    window_seconds: int | None = Query(None, ge=1, le=86400),
    admin: Principal = Depends(administrator),
    monitor: MonitorService = Depends(monitor_service),
) -> ApiResponse[Any]:
    return answer(
        monitor.llm_stats() if window_seconds is None else monitor.llm_stats(window_seconds)
    )


@router.get("/metrics/cache-stats")
def cache_stats(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.probes.cache_stats(monitor.cache))


@router.get("/config/strategies")
def strategies(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer({"strategies": monitor.probes.strategies()})


@router.get("/config/providers")
def providers(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.probes.providers())


@router.get("/config/sandbox")
def sandbox_config(
    admin: Principal = Depends(administrator), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.probes.sandbox_config())


@router.get("/quotas")
@router.get("/quotas/usage")
def quotas(
    principal: Principal = Depends(current_user), monitor: MonitorService = Depends(monitor_service)
) -> ApiResponse[Any]:
    return answer(monitor.quotas(principal.user_id))


@router.get("/logs")
def global_logs(
    filters: dict[str, Any] = Depends(log_filters),
    admin: Principal = Depends(administrator),
    monitor: MonitorService = Depends(monitor_service),
) -> ApiResponse[Any]:
    items, total = monitor.store.query_logs(**filters)
    return answer(
        {
            "items": items,
            "total": total,
            "limit": filters["limit"],
            "offset": filters["offset"],
            "source": "retained_api_and_task_events",
        }
    )


def owned_logs(
    monitor: MonitorService, run_id: str, principal: Principal, filters: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    run_id = monitor.owned_log_key(run_id, principal.user_id)
    return monitor.store.query_logs(**filters, user_id=principal.user_id, run_id=run_id)


@router.get("/logs/tasks/{task_id}")
def task_logs(
    task_id: str,
    filters: dict[str, Any] = Depends(log_filters),
    principal: Principal = Depends(current_user),
    monitor: MonitorService = Depends(monitor_service),
) -> ApiResponse[Any]:
    items, total = owned_logs(monitor, task_id, principal, filters)
    return answer(
        {
            "task_id": task_id,
            "items": items,
            "total": total,
            "limit": filters["limit"],
            "offset": filters["offset"],
            "source": "retained_api_lifecycle_and_trusted_task_events",
        }
    )


@router.get("/logs/download/{task_id}")
def download_logs(
    task_id: str,
    filters: dict[str, Any] = Depends(log_filters),
    principal: Principal = Depends(current_user),
    monitor: MonitorService = Depends(monitor_service),
) -> Response:
    # The ID is first resolved through the owned run mapping; do not use it as
    # a path or raw Content-Disposition value.
    run_id = monitor.owned_log_key(task_id, principal.user_id)
    stream = cast(BinaryIO, SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b"))
    try:
        summary = monitor.store.export_logs(
            stream,
            **{key: value for key, value in filters.items() if key not in {"limit", "offset"}},
            user_id=principal.user_id,
            run_id=run_id,
        )
        stream.seek(0)
        return LogDownloadResponse(
            stream,
            headers={
                "Content-Disposition": "attachment; filename=task-logs.jsonl",
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Retained-Log-Count": str(summary["total"]),
                "X-Exported-Log-Count": str(summary["exported"]),
                "X-Log-Export-Truncated": str(summary["truncated"]).lower(),
            },
        )
    except BaseException:
        stream.close()
        raise
