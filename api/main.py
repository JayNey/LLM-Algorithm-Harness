"""FastAPI application setup and configuration."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth.config import AuthSettings
from api.auth.middleware import AuthBoundaryMiddleware
from api.auth.service import AuthService
from api.config import settings
from api.middleware.errors import setup_error_handlers
from api.middleware.logging import setup_logging_middleware
from api.routes import evaluations_router
from api.routes.auth import router as auth_router
from api.services import EvaluationService


def create_app(auth_settings: AuthSettings | None = None) -> FastAPI:
    """Create and configure FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.auth = AuthService(auth_settings or AuthSettings())
        app.state.evaluations = EvaluationService()
        yield

    app = FastAPI(
        title="LLM Algorithm Harness API",
        description="REST API for LLM algorithm evaluation harness",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Setup logging and error handlers
    setup_logging_middleware(app)
    app.add_middleware(AuthBoundaryMiddleware)
    setup_error_handlers(app)

    # Include routers
    app.include_router(evaluations_router)
    app.include_router(auth_router)

    @app.get("/api/v1/health")
    def health_check():
        """Health check endpoint."""
        return {
            "success": True,
            "data": {
                "status": "healthy",
                "version": "0.1.0",
                "service": "LLM Algorithm Harness API",
            },
            "message": "Service is healthy",
        }

    return app


# Create application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
