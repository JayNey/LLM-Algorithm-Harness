"""FastAPI application setup and configuration."""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, suppress
from typing import Any, cast

from fastapi import FastAPI, Request
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from api.auth.config import AuthSettings
from api.auth.middleware import AuthBoundaryMiddleware
from api.auth.service import AuthService
from api.config import settings
from api.db.engine import get_db
from api.documentation import install_documentation
from api.files.config import FileSettings
from api.files.middleware import UploadBoundaryMiddleware
from api.files.service import FileService
from api.middleware.errors import ErrorCORSMiddleware, error_responses, setup_error_handlers
from api.middleware.logging import setup_logging_middleware
from api.monitoring.config import MonitorSettings
from api.monitoring.service import MonitorService
from api.progress import ProgressStream, RedisProgressStream
from api.routes import evaluation_results_router, evaluations_router, tasks_router
from api.routes.ab_tests import router as ab_tests_router
from api.routes.auth import router as auth_router
from api.routes.benchmarks import router as benchmarks_router
from api.routes.costs import router as costs_router
from api.routes.experiments import router as experiments_router
from api.routes.files import router as files_router
from api.routes.monitoring import router as monitoring_router
from api.routes.ws import router as ws_router
from api.services import (
    ABTestService,
    BenchmarkService,
    CostService,
    EvaluationResultsService,
    EvaluationService,
    ExperimentService,
)
from src.ab_testing import ABTestRunner
from src.benchmark.executor import BenchmarkExecutor
from src.experiment import ExperimentRunner


def task_database(request: Request) -> Iterator[Session]:
    """Bind HTTP task sessions to this app rather than a mutable global factory."""
    factory = cast(sessionmaker[Session], request.app.state.task_session_factory)
    with factory() as session:
        yield session


def create_app(
    auth_settings: AuthSettings | None = None,
    file_settings: FileSettings | None = None,
    database_url: str | None = None,
    experiment_runner_factory: Any = None,
    benchmark_executor_factory: Any = None,
    ab_test_runner_factory: Any = None,
    *,
    monitor_settings: MonitorSettings | None = None,
    progress_stream: ProgressStream | None = None,
) -> FastAPI:
    """Create and configure FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from api.db.engine import (
            business_database_url,
            make_engine,
            make_session_factory,
            set_session_factory,
        )

        # Initialize database session factory
        db_url = database_url or business_database_url()
        engine = make_engine(db_url)
        session_factory = make_session_factory(engine)
        set_session_factory(session_factory)
        app.state.task_engine = engine
        app.state.task_session_factory = session_factory

        app.state.auth = AuthService(auth_settings or AuthSettings())
        app.state.evaluations = EvaluationService(database_url)
        app.state.evaluation_results = EvaluationResultsService(database_url)
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
        app.state.cost = CostService(database_url)
        app.state.progress_stream = progress_stream or RedisProgressStream()
        app.state.files = FileService(app.state.auth, file_settings or FileSettings())
        app.state.monitor = MonitorService(
            app.state.auth,
            app.state.files,
            app.state.evaluations,
            monitor_settings or MonitorSettings(),
            task_engine=engine,
        )
        app.state.auth.audit_sink = app.state.monitor.audit_event
        await run_in_threadpool(app.state.files.cleanup)

        async def cleanup_files() -> None:
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
            app.state.monitor.close()
            app.state.evaluations.close()
            engine.dispose()

    app = FastAPI(
        title="LLM Algorithm Harness API",
        description="REST API for LLM algorithm evaluation harness",
        version="0.1.0",
        responses=error_responses(),
        lifespan=lifespan,
    )
    app.dependency_overrides[get_db] = task_database

    # CORS covers early auth/quota rejection responses. Logging wraps CORS and
    # the upload boundary, including preflight and final 413 responses.
    app.add_middleware(UploadBoundaryMiddleware)
    app.add_middleware(AuthBoundaryMiddleware)
    setup_error_handlers(app)
    app.add_middleware(
        ErrorCORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    setup_logging_middleware(app)

    # Include routers
    app.include_router(evaluations_router)
    app.include_router(evaluation_results_router)
    app.include_router(tasks_router)
    app.include_router(auth_router)
    app.include_router(files_router)
    app.include_router(monitoring_router)
    app.include_router(experiments_router)
    app.include_router(benchmarks_router)
    app.include_router(ab_tests_router)
    app.include_router(costs_router)
    app.include_router(ws_router)

    @app.get("/api/v1/health")
    def health_check() -> dict[str, Any]:
        """Health check endpoint."""
        return {
            "success": True,
            "data": {
                "status": "healthy",
                "scope": "api_liveness_only",
                "version": "0.1.0",
                "service": "LLM Algorithm Harness API",
            },
            "message": "Service is healthy",
        }

    install_documentation(app)
    return app


# Create application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
