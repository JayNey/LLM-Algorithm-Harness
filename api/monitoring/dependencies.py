"""Server-selected administrators; existing user authentication remains mandatory."""

from typing import cast

from fastapi import Depends, HTTPException, Request

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.monitoring.service import MonitorService


def monitor_service(request: Request) -> MonitorService:
    return cast(MonitorService, request.app.state.monitor)


def administrator(
    principal: Principal = Depends(current_user), monitor: MonitorService = Depends(monitor_service)
) -> Principal:
    if not monitor.settings.is_admin(principal.user_id):
        raise HTTPException(403, "Administrator permission required")
    return principal
