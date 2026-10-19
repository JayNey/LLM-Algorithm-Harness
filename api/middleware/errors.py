"""HTTP error contract shared by exception handlers and early ASGI boundaries."""

import logging
import uuid
from collections.abc import Mapping
from enum import Enum
from http import HTTPStatus
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.utils.secrets import is_sensitive_key, redact_sensitive_data, redact_sensitive_text

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INVALID_TOKEN = "INVALID_TOKEN"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    TASK_ALREADY_RUNNING = "TASK_ALREADY_RUNNING"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    HTTP_ERROR = "HTTP_ERROR"


HTTP_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_PARAMETER,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    408: ErrorCode.REQUEST_TIMEOUT,
    409: ErrorCode.DUPLICATE_RESOURCE,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    429: ErrorCode.RATE_LIMIT_EXCEEDED,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    details: Any = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorDetail
    message: str = Field(description="Compatibility alias of error.message")
    detail: Any = Field(description="Compatibility HTTPException detail")
    details: Any = Field(default_factory=dict, description="Compatibility alias of error.details")


class ApiError(HTTPException):
    """Explicit machine-readable code, without inferring meaning from messages."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode | str = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        *,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(status_code, detail=message, headers=headers)
        self.message = message
        self.error_code = ErrorCode(error_code)
        self.details = details if details is not None else {}


class ValidationApiError(ApiError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, ErrorCode.INVALID_PARAMETER, 400, details=details)


class NotFoundError(ApiError):
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.RESOURCE_NOT_FOUND, 404)


class ConflictError(ApiError):
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.DUPLICATE_RESOURCE, 409)


def request_id(scope: Scope) -> str:
    """Generate once per HTTP scope; never reflect untrusted request headers."""
    state = scope.setdefault("state", {})
    if "request_id" not in state:
        state["request_id"] = "req_" + uuid.uuid4().hex
    return str(state["request_id"])


def error_response(
    scope: Scope,
    status_code: int,
    detail: Any = None,
    *,
    code: ErrorCode | None = None,
    details: Any = None,
    field_errors: dict[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build errors before a response starts, preserving protocol headers."""
    code = code or HTTP_CODES.get(
        status_code, ErrorCode.INTERNAL_ERROR if status_code >= 500 else ErrorCode.HTTP_ERROR
    )
    if status_code >= 500:
        message = "Service is unavailable" if status_code == 503 else "An unexpected error occurred"
        public_detail, public_details = message, {}
    else:
        fallback = (
            HTTPStatus(status_code).phrase
            if status_code in HTTPStatus._value2member_map_
            else "Request failed"
        )
        public_detail = redact_sensitive_data(detail if detail is not None else fallback)
        if isinstance(public_detail, str):
            message = public_detail or fallback
        elif isinstance(public_detail, dict) and isinstance(public_detail.get("message"), str):
            message = public_detail["message"] or fallback
        else:
            message = fallback
        if field_errors is not None:
            # These are sanitized validation messages, not credential values.
            public_details = field_errors
        elif details is not None:
            public_details = redact_sensitive_data(details)
        elif isinstance(public_detail, dict):
            public_details = {
                key: value for key, value in public_detail.items() if key != "message"
            }
        else:
            public_details = {}
    identity = request_id(scope)
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=public_details, request_id=identity),
        message=message,
        detail=public_detail,
        details=public_details,
    )
    response_headers = {"Cache-Control": "no-store", **(headers or {}), "X-Request-ID": identity}
    return JSONResponse(
        status_code=status_code, content=body.model_dump(mode="json"), headers=response_headers
    )


def error_responses() -> dict[int | str, dict[str, Any]]:
    """Common OpenAPI models, including the real 400 validation contract."""
    responses: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorResponse} for status in HTTP_CODES
    }
    responses.update({"4XX": {"model": ErrorResponse}, "5XX": {"model": ErrorResponse}})
    return responses


def internal_error_response(scope: Scope, exc: Exception) -> JSONResponse:
    logger.error("Unhandled API error request_id=%s type=%s", request_id(scope), type(exc).__name__)
    return error_response(scope, 500)


class ErrorBoundaryMiddleware:
    """Consume failures before headers so servers cannot log raw exceptions."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            if started:
                raise
            await internal_error_response(scope, exc)(scope, receive, send)


class ErrorCORSMiddleware(CORSMiddleware):
    """Keep Starlette's CORS decisions, format only rejected preflight bodies."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "OPTIONS":
            headers = Headers(scope=scope)
            if "origin" in headers and "access-control-request-method" in headers:
                response = self.preflight_response(headers)
                if response.status_code >= 400:
                    policy_headers = {
                        key: value
                        for key, value in response.headers.items()
                        if key.lower() not in {"content-type", "content-length"}
                    }
                    response = error_response(
                        scope,
                        response.status_code,
                        bytes(response.body).decode("utf-8"),
                        headers=policy_headers,
                    )
                await response(scope, receive, send)
                return
        await super().__call__(scope, receive, send)


def setup_error_handlers(app: FastAPI) -> FastAPI:
    app.add_middleware(ErrorBoundaryMiddleware)

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(
            request.scope,
            exc.status_code,
            exc.detail,
            code=exc.error_code,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(request.scope, exc.status_code, exc.detail, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Exclude input/ctx: they can contain secrets or non-JSON objects.
        failures = exc.errors()
        known_secrets = [
            item["input"]
            for item in failures
            if item["loc"]
            and is_sensitive_key(item["loc"][-1])
            and isinstance(item.get("input"), str)
        ]
        errors = {
            ".".join(str(part) for part in item["loc"][1:]): redact_sensitive_text(
                item["msg"], known_secrets
            )
            for item in failures
        }
        return error_response(request.scope, 400, "Request validation failed", field_errors=errors)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return internal_error_response(request.scope, exc)

    return app
