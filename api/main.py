"""FastAPI application setup and configuration."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from api.auth.config import AuthSettings
from api.auth.middleware import AuthBoundaryMiddleware
from api.auth.service import AuthService
from api.config import settings
from api.files.config import FileSettings
from api.files.middleware import UploadBoundaryMiddleware
from api.files.service import FileService
from api.middleware.errors import setup_error_handlers
from api.middleware.logging import setup_logging_middleware
from api.routes import evaluations_router, tasks_router
from api.routes.ab_tests import router as ab_tests_router
from api.routes.auth import router as auth_router
from api.routes.benchmarks import router as benchmarks_router
from api.routes.experiments import router as experiments_router
from api.routes.files import router as files_router
from api.services import (
    ABTestService,
    BenchmarkService,
    EvaluationService,
    ExperimentService,
)
from src.ab_testing import ABTestRunner
from src.benchmark.executor import BenchmarkExecutor
from src.experiment import ExperimentRunner


def create_app(
    auth_settings: AuthSettings | None = None,
    file_settings: FileSettings | None = None,
    database_url: str | None = None,
    experiment_runner_factory: Any = None,
    benchmark_executor_factory: Any = None,
    ab_test_runner_factory: Any = None,
) -> FastAPI:
    """Create and configure FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.auth = AuthService(auth_settings or AuthSettings())
        app.state.evaluations = EvaluationService(database_url)
        app.state.experiments = ExperimentService(
            database_url,
            auth=app.state.auth,
            runner_factory=experiment_runner_factory or ExperimentRunner,
        )
        app.state.benchmarks = BenchmarkService(
            database_url,
            auth=app.state.auth,
            executor_factory=benchmark_executor_factory or BenchmarkExecutor,
        )
        app.state.ab_tests = ABTestService(
            database_url,
            auth=app.state.auth,
            runner_factory=ab_test_runner_factory or ABTestRunner,
        )
        app.state.files = FileService(app.state.auth, file_settings or FileSettings())
        await run_in_threadpool(app.state.files.cleanup)

        async def cleanup_files():
            while True:
                await asyncio.sleep(app.state.files.settings.FILE_CLEANUP_INTERVAL_SECONDS)
                try:
                    await run_in_threadpool(app.state.files.cleanup)
                except Exception:
                    logging.getLogger(__name__).warning("file_cleanup_failed")

        cleaner = asyncio.create_task(cleanup_files())
        try:
            yield
        finally:
            cleaner.cancel()
            with suppress(asyncio.CancelledError):
                await cleaner
            app.state.evaluations.close()

    app = FastAPI(
        title="LLM Algorithm Harness API",
        description="REST API for LLM algorithm evaluation harness",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Direct ASGI logging stays outside the upload boundary so it records the
    # final 413 response. CORS also covers early auth/quota rejection responses.
    app.add_middleware(UploadBoundaryMiddleware)
    app.add_middleware(AuthBoundaryMiddleware)
    setup_logging_middleware(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    setup_error_handlers(app)

    # Include routers
    app.include_router(evaluations_router)
    app.include_router(tasks_router)
    app.include_router(auth_router)
    app.include_router(files_router)
    app.include_router(experiments_router)
    app.include_router(benchmarks_router)
    app.include_router(ab_tests_router)

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
