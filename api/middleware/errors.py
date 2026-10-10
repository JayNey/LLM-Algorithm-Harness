"""Global error handlers for FastAPI."""

import logging
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Base API error class."""

    def __init__(self, message: str, error_code: str = "internal_error", status_code: int = 500):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)


class ValidationApiError(ApiError):
    """Validation error."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "validation_error", status.HTTP_400_BAD_REQUEST)
        self.details = details or {}


class NotFoundError(ApiError):
    """Resource not found error."""

    def __init__(self, message: str):
        super().__init__(message, "not_found", status.HTTP_404_NOT_FOUND)


class ConflictError(ApiError):
    """Conflict error (e.g., task already running)."""

    def __init__(self, message: str):
        super().__init__(message, "conflict", status.HTTP_400_BAD_REQUEST)


def setup_error_handlers(app: FastAPI):
    """Register global error handlers."""

    @app.exception_handler(ApiError)
    async def api_error_handler(request, exc: ApiError):
        """Handle custom API errors."""
        response = {
            "success": False,
            "error": exc.error_code,
            "message": exc.message,
        }
        if isinstance(exc, ValidationApiError) and exc.details:
            response["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=response)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc: RequestValidationError):
        """Handle Pydantic validation errors."""
        errors = {}
        for error in exc.errors():
            field = ".".join(str(x) for x in error["loc"][1:])
            errors[field] = error["msg"]

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": "validation_error",
                "message": "Request validation failed",
                "details": errors,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        """Handle unexpected exceptions."""
        logger.exception("Unexpected error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "internal_error",
                "message": "An unexpected error occurred",
            },
        )

    return app
