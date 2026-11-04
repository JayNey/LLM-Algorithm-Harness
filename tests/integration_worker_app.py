"""Celery entry used only by the real-worker integration test.

The worker process imports this module. Production code keeps using
``src.celery_app``. Patches replace credential lookup, sandbox preflight,
model execution, and pricing so the real evaluation orchestration can finish
without a provider or a sandbox.
"""

import os
from pathlib import Path

# Celery's fast trace state is inherited by fork; macOS defaults to spawn.
if os.environ.get("EVALUATION_TEST_CRASH_MARKER"):
    import billiard

    billiard.set_start_method("fork", force=True)

from pydantic import SecretStr

from api.auth.service import AuthService
from src.celery_app import celery_app
from src.harness import AlgorithmHarness
from src.models import CacheConfig, ExecutionResult, LLMConfig

__all__ = ["celery_app"]


def _llm_config(self: AuthService, key_id: str, user_id: str, model: str) -> LLMConfig:
    """Return a local credential without reading the auth store."""
    del self, key_id, user_id
    return LLMConfig(
        provider="openai",
        api_key=SecretStr("sk-test"),
        model=model,
        timeout=5,
        retry_max_attempts=1,
        cache=CacheConfig(enabled=False),
    )


def _prepare_strategy_runtime(
    self: AlgorithmHarness, strategy_config: object
) -> tuple[object, object]:
    """Skip sandbox preflight."""
    del self, strategy_config
    return (object(), object())


def _execute_problem(
    self: AlgorithmHarness,
    strategy_config: object,
    problem: object,
    strategy: object,
    sandbox: object,
) -> ExecutionResult:
    """Return one successful local result."""
    del self, strategy, sandbox
    if calls := os.environ.get("EVALUATION_TEST_CALLS"):
        with Path(calls).open("a") as stream:
            stream.write(problem.problem_id + "\n")
    return ExecutionResult(
        problem_id=problem.problem_id,
        strategy=strategy_config.name,
        generated_code="def solution(**kw):\n    return 1",
        status="success",
        total_tokens=10,
        execution_time_seconds=0.5,
        difficulty="easy",
    )


def _estimate_cost(
    self: AlgorithmHarness, results: list[ExecutionResult]
) -> tuple[float, dict[str, bool]]:
    """Return a known price so the task can record spend."""
    del self, results
    return (0.01, {"unknown_usage": False, "unknown_pricing": False})


AuthService.llm_config = _llm_config
AlgorithmHarness._prepare_strategy_runtime = _prepare_strategy_runtime
AlgorithmHarness._execute_problem = _execute_problem
AlgorithmHarness._estimate_cost = _estimate_cost


# Test-only fault hook: kill the actual pool child after its file commit.
if marker := os.environ.get("EVALUATION_TEST_CRASH_MARKER"):
    from src.tasks import evaluation

    _record_result = evaluation._record_unit_result

    def _crash_before_sql(db, ev, unit):
        try:
            with Path(marker).open("x") as stream:
                stream.write(str(os.getpid()))
        except FileExistsError:
            return _record_result(db, ev, unit)
        os._exit(73)

    evaluation._record_unit_result = _crash_before_sql
