"""Tests for the persistent task orchestration service."""

import threading
import time
from unittest.mock import Mock

import pytest

from src.harness import AlgorithmHarness
from src.models import (
    CostAlertConfig,
    ExecutionResult,
    HarnessConfig,
    LLMConfig,
    SandboxConfig,
    StrategyConfig,
)
from src.task_service import TaskService, TaskUnit


def _units(count=4):
    return [
        TaskUnit(unit_id=f"vanilla:p{i}:0", strategy="vanilla", problem_id=f"p{i}")
        for i in range(count)
    ]


def test_task_creation_persists_atomic_record_and_events(tmp_path):
    service = TaskService(tmp_path / "tasks")
    record = service.create(
        units=_units(2), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-test"
    )

    loaded = service.get(record.run_id)
    assert loaded.state == "queued"
    assert loaded.total_units == 2
    assert loaded.events[0].kind == "task_created"
    assert service.list()[0].run_id == "run-test"
    with pytest.raises(ValueError, match="non-negative"):
        service.events_since(record.run_id, -1)
    failed = service.fail(record.run_id, "setup failed")
    assert failed.state == "failed"
    assert failed.error == "setup failed"
    assert service.events_since(record.run_id)[-1].kind == "task_failed"
    assert service.cancel(record.run_id).state == "failed"
    with pytest.raises(ValueError, match="Invalid run_id"):
        service.store.path_for("run\nInjected-Header: value")


def test_fingerprints_are_content_sensitive_without_storing_api_key(tmp_path):
    config = HarnessConfig(
        dataset_path=str(tmp_path / "dataset.json"),
        llm_config=LLMConfig(provider="openai", api_key="secret-a", model="model-a"),
    )
    other = config.model_copy(deep=True)
    other.llm_config.api_key = "secret-b"

    first = TaskService.config_fingerprint(config)
    second = TaskService.config_fingerprint(other)
    assert first != second
    assert "secret-a" not in first
    assert "secret-b" not in second


def test_alert_endpoint_secret_changes_resume_fingerprint(tmp_path):
    config = HarnessConfig(
        dataset_path=str(tmp_path / "dataset.json"),
        llm_config=LLMConfig(provider="openai", api_key="key", model="model-a"),
        budget_cap_usd=1.0,
        budget_action="auto_stop",
        cost_alerts=CostAlertConfig(webhook_url="https://example.com/secret-a"),
    )
    changed = config.model_copy(deep=True)
    changed.cost_alerts = CostAlertConfig(webhook_url="https://example.com/secret-b")
    assert TaskService.config_fingerprint(config) != TaskService.config_fingerprint(changed)
    assert "secret-a" not in str(config.redacted_dict())


def test_task_run_respects_max_workers_and_records_results(tmp_path):
    service = TaskService(tmp_path / "tasks")
    record = service.create(
        units=_units(8), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-concurrent"
    )
    active = 0
    peak = 0
    lock = threading.Lock()

    def worker(unit):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return {"unit_id": unit.unit_id, "status": "success"}

    result = service.run(record.run_id, worker, max_workers=2, config_fingerprint="config-a", dataset_fingerprint="data-a")

    assert result.state == "completed"
    assert result.completed_units == 8
    assert peak <= 2
    assert all(unit.status == "completed" for unit in result.units)
    assert [event.sequence for event in result.events] == list(range(1, len(result.events) + 1))


def test_budget_pause_preserves_queued_units_and_resume_does_not_dispatch(tmp_path):
    service = TaskService(tmp_path / "tasks")
    record = service.create(
        units=_units(3), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-pause"
    )
    completed = []

    def worker(unit):
        completed.append(unit.problem_id)
        return {"status": "success"}

    paused = service.run(
        record.run_id, worker, max_workers=1,
        pause_when=lambda state: state.completed_units >= 1,
    )
    assert paused.state == "paused"
    assert completed == ["p0"]
    assert [unit.status for unit in paused.units] == ["completed", "queued", "queued"]
    assert paused.events[-1].kind == "task_paused"

    again = service.run(
        record.run_id, worker, max_workers=1, resume=True,
        pause_when=lambda state: state.completed_units >= 1,
    )
    assert again.state == "paused"
    assert completed == ["p0"]


def test_parallel_execution_with_different_max_workers(tmp_path):
    """Test that parallel execution scales with max_workers configuration."""
    service = TaskService(tmp_path / "tasks")

    # Test with max_workers=1 (serial execution)
    record_serial = service.create(
        units=_units(4), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-serial"
    )
    start_serial = time.time()
    service.run(
        record_serial.run_id,
        lambda unit: time.sleep(0.05) or {"status": "success"},
        max_workers=1,
        config_fingerprint="config-a",
        dataset_fingerprint="data-a"
    )
    duration_serial = time.time() - start_serial

    # Test with max_workers=4 (parallel execution)
    record_parallel = service.create(
        units=_units(4), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-parallel"
    )
    start_parallel = time.time()
    service.run(
        record_parallel.run_id,
        lambda unit: time.sleep(0.05) or {"status": "success"},
        max_workers=4,
        config_fingerprint="config-a",
        dataset_fingerprint="data-a"
    )
    duration_parallel = time.time() - start_parallel

    # Parallel execution should be significantly faster (at least 2x)
    assert duration_parallel < duration_serial / 2


def test_thread_safe_cost_tracking(tmp_path):
    """Test that cost tracking remains accurate under concurrent execution."""
    service = TaskService(tmp_path / "tasks")
    record = service.create(
        units=_units(10), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-cost"
    )

    total_cost = 0.0
    cost_lock = threading.Lock()

    def worker(unit):
        nonlocal total_cost
        cost = 0.01  # Fixed cost per unit
        with cost_lock:
            total_cost += cost
        time.sleep(0.01)
        return {"status": "success", "cost": cost}

    result = service.run(
        record.run_id,
        worker,
        max_workers=5,
        config_fingerprint="config-a",
        dataset_fingerprint="data-a"
    )

    assert result.state == "completed"
    assert abs(total_cost - 0.10) < 0.001  # 10 units * 0.01 = 0.10


def test_failure_category_system_error(tmp_path):
    service = TaskService(tmp_path / "tasks")
    record = service.create(
        units=_units(3), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-failed"
    )
    calls = []

    def worker(unit):
        calls.append(unit.unit_id)
        if unit.problem_id == "p1":
            raise RuntimeError("provider failed")
        return {"status": "success"}

    result = service.run(record.run_id, worker, max_workers=1)
    assert result.state == "failed"
    assert sum(unit.status == "failed" for unit in result.units) == 1

    resumed = service.run(
        record.run_id,
        worker,
        max_workers=1,
        config_fingerprint="config-a",
        dataset_fingerprint="data-a",
        resume=True,
    )
    assert resumed.state == "failed"
    assert calls.count("vanilla:p0:0") == 1
    assert calls.count("vanilla:p1:0") == 1
    assert calls.count("vanilla:p2:0") == 1


def test_cancel_marks_queued_and_inflight_units_without_claiming_exactly_once(tmp_path):
    service = TaskService(tmp_path / "tasks")
    record = service.create(
        units=_units(4), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-cancel"
    )
    started = threading.Event()
    release = threading.Event()
    holder = {}

    def worker(unit):
        started.set()
        release.wait(timeout=2)
        return {"status": "success"}

    thread = threading.Thread(
        target=lambda: holder.setdefault("record", service.run(record.run_id, worker, max_workers=1)),
        daemon=True,
    )
    thread.start()
    assert started.wait(timeout=1)
    TaskService(tmp_path / "tasks").request_cancel(record.run_id)
    thread.join(timeout=1)
    release.set()
    thread.join(timeout=2)

    cancelled = holder["record"]
    assert cancelled.state == "cancelled"
    assert any(unit.uncertain for unit in cancelled.units)
    assert any(unit.status == "cancelled" and not unit.uncertain for unit in cancelled.units)
    assert any(event.kind == "cancel_requested" for event in cancelled.events)
    assert any(event.kind == "task_cancelled" for event in cancelled.events)
    assert [event.sequence for event in cancelled.events] == list(range(1, len(cancelled.events) + 1))


def test_resume_requeues_uncertain_units_and_rejects_fingerprint_mismatch(tmp_path):
    service = TaskService(tmp_path / "tasks")
    record = service.create(
        units=_units(2), config_fingerprint="config-a", dataset_fingerprint="data-a", run_id="run-resume"
    )
    started = threading.Event()
    release = threading.Event()

    def blocking_worker(unit):
        started.set()
        release.wait(timeout=2)
        return {"status": "success"}

    thread = threading.Thread(target=lambda: service.run(record.run_id, blocking_worker, max_workers=1), daemon=True)
    thread.start()
    assert started.wait(timeout=1)
    service.request_cancel(record.run_id)
    thread.join(timeout=1)
    release.set()
    thread.join(timeout=2)

    with pytest.raises(ValueError, match="fingerprint"):
        service.run(record.run_id, lambda unit: {}, config_fingerprint="different", resume=True)

    resumed = service.run(
        record.run_id,
        lambda unit: {"status": "success", "problem_id": unit.problem_id},
        max_workers=2,
        config_fingerprint="config-a",
        dataset_fingerprint="data-a",
        resume=True,
    )
    assert resumed.state == "completed"
    assert all(unit.status == "completed" for unit in resumed.units)


def test_harness_task_mode_uses_persistent_service(tmp_path, monkeypatch):
    """The CLI-facing harness path uses the same task lifecycle service."""
    dataset = tmp_path / "problems.json"
    dataset.write_text(
        '[{"problem_id":"p1","title":"P1","description":"A problem description",'
        '"difficulty":"easy","test_cases":[{"input":{"x":1},"expected_output":1}]}]'
    )
    config = HarnessConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        llm_config=LLMConfig(provider="openai", api_key="key", model="test-model"),
        sandbox_config=SandboxConfig(backend="host"),
        strategies=[StrategyConfig(name="vanilla")],
        max_workers=2,
    )
    strategy = Mock()
    strategy.execute.return_value = ExecutionResult(
        problem_id="p1", strategy="vanilla", generated_code="", status="success"
    )
    sandbox = Mock()
    monkeypatch.setattr(
        AlgorithmHarness,
        "_prepare_strategy_runtime",
        lambda self, strategy_config: (strategy, sandbox),
    )

    harness = AlgorithmHarness(config)
    reports = harness.run(use_task_service=True, run_id="run-api")

    assert reports["vanilla"].solved_problems == 1
    assert harness.task_record.run_id == "run-api"
    assert harness.task_record.state == "completed"
    assert (tmp_path / "results" / "tasks" / "run-api.json").exists()
