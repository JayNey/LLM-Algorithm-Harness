"""Current-user in-app notification routes (issue #328)."""

from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.schemas import ApiResponse
from api.services.in_app_notification_service import NotificationNotFound, NotificationService

router = APIRouter(prefix="/api/v1", tags=["notifications"])


def notification_service(request: Request) -> NotificationService:
    return cast(NotificationService, request.app.state.notifications)


def _call(operation):
    try:
        return operation()
    except NotificationNotFound as exc:
        raise HTTPException(404, "Notification not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/notifications")
def list_notifications(
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = None,
    kind: str | None = None,
    unread: bool | None = None,
    principal: Principal = Depends(current_user),
    service: NotificationService = Depends(notification_service),
) -> ApiResponse[dict]:
    result = _call(
        lambda: service.list_notifications(
            principal.user_id, limit=limit, cursor=cursor, kind=kind, unread=unread
        )
    )
    return ApiResponse(success=True, data=result, message="Notifications retrieved successfully")


@router.get("/notifications/unread-count")
def notification_unread_count(
    principal: Principal = Depends(current_user),
    service: NotificationService = Depends(notification_service),
) -> ApiResponse[dict]:
    count = service.unread_count(principal.user_id)
    return ApiResponse(
        success=True,
        data={"unread_count": count},
        message="Unread notification count retrieved successfully",
    )


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    before: datetime | None = None,
    principal: Principal = Depends(current_user),
    service: NotificationService = Depends(notification_service),
) -> ApiResponse[dict]:
    result = service.mark_all_read(principal.user_id, before)
    return ApiResponse(success=True, data=result, message="Notifications marked read successfully")


@router.post("/notifications/clear")
def clear_notifications(
    before: datetime | None = None,
    principal: Principal = Depends(current_user),
    service: NotificationService = Depends(notification_service),
) -> ApiResponse[dict]:
    result = service.clear(principal.user_id, before)
    return ApiResponse(success=True, data=result, message="Notifications cleared successfully")


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    principal: Principal = Depends(current_user),
    service: NotificationService = Depends(notification_service),
) -> ApiResponse[dict]:
    result = _call(lambda: service.mark_read(principal.user_id, notification_id))
    return ApiResponse(success=True, data=result, message="Notification marked read successfully")
