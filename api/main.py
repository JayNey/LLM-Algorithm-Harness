"""FastAPI application setup and configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.middleware.errors import setup_error_handlers
from api.middleware.logging import setup_logging_middleware
from api.routes import evaluations_router


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="LLM Algorithm Harness API",
        description="REST API for LLM algorithm evaluation harness",
        version="0.1.0",
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Setup logging and error handlers
    setup_logging_middleware(app)
    setup_error_handlers(app)

    # Include routers
    app.include_router(evaluations_router)

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
