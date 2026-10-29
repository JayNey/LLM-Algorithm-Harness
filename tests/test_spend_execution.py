"""Real client/runner accounting, with only the external provider stubbed."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from api.db import make_engine, make_session_factory, run_migrations
from api.db.models import ABTest, Experiment, PricingOverride, SpendRecord
from api.services.spend_records import SpendRecorder, pricing_snapshot
from src.ab_testing import ABTestConfig, ABTestRunner, PromptVariant
from src.experiment import ExperimentRunner
from src.llm_client import LLMClient
from src.models import ExperimentConfig, LLMConfig, SandboxConfig, StrategyConfig


def dataset(tmp_path, count=2):
    path = tmp_path / "problems.json"
    path.write_text(
        json.dumps(
            [
                {
                    "problem_id": f"p{i}",
                    "title": "Plus one",
                    "description": "Return the input integer plus one.",
                    "difficulty": "easy",
                    "tags": [],
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                }
                for i in range(count)
            ]
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def execution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = make_engine(f"sqlite:///{tmp_path}/spend.sqlite3")
    run_migrations(engine)
    factory = make_session_factory(engine)
    with factory() as db, db.begin():
        db.add(Experiment(id="experiment", user_id="alice", config={}))
        db.add(ABTest(id="ab", user_id="alice", config={}))
        db.add(
            PricingOverride(
                id="price",
                model="priced/model",
                prompt_per_1k=1,
                completion_per_1k=4,
                created_by="alice",
            )
        )
    yield factory
    engine.dispose()


def provider_client(monkeypatch, *, after_call=None, fail=False):
    def create(**_kwargs):
        if fail:
            raise RuntimeError("provider stopped")
        if after_call is not None:
            after_call()
        return SimpleNamespace(
            model="priced/model",
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="```python\ndef solution(x): return x + 1\n```"
                    ),
                    finish_reason="stop",
                )
            ],
        )

    monkeypatch.setattr(
        LLMClient,
        "_initialize_client",
        lambda _: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            base_url="https://provider.invalid/v1",
        ),
    )


def config_model(*, cache=False):
    return LLMConfig(
        provider="openai",
        api_key="test-only",
        model="priced/model",
        cache={"enabled": cache},
        retry_max_attempts=1,
    )


def attach(runner, factory, source, job):
    recorder = SpendRecorder(factory, source, job, "alice")
    runner.pricing_manager = pricing_snapshot(factory)
    runner.on_spend = lambda eid, reply, cached, context: recorder.callback(**context)(
        eid, reply, cached
    )


@pytest.mark.parametrize("kind", ["experiment", "ab"])
def test_real_runners_persist_before_finish_and_skip_checkpoints_on_resume(
    execution, tmp_path, monkeypatch, kind
):
    provider_client(monkeypatch)
    data = dataset(tmp_path)
    if kind == "experiment":
        runner = ExperimentRunner(
            ExperimentConfig(
                dataset_path=str(data),
                output_dir=str(tmp_path / "results"),
                models=[config_model()],
                strategies=[StrategyConfig(name="vanilla")],
                sandbox_config=SandboxConfig(backend="host"),
            )
        )
        source, job = "experiments", "experiment"
        # Report rendering is independent of recording and needs no graphical backend here.
        monkeypatch.setattr("src.experiment.generate_comparison_report", lambda _: None)
        monkeypatch.setattr("src.experiment.generate_html_panel", lambda _: None)
    else:
        runner = ABTestRunner(
            ABTestConfig(
                dataset_path=str(data),
                output_dir=str(tmp_path / "results"),
                model=config_model(),
                strategy=StrategyConfig(name="vanilla"),
                prompt_variants=[PromptVariant(id="a"), PromptVariant(id="b")],
                sandbox_config=SandboxConfig(backend="host"),
            )
        )
        source, job = "ab_tests", "ab"
    runner.checkpoint_dir = tmp_path / "checkpoint"
    attach(runner, execution, source, job)
    runner.run()
    with execution() as db:
        rows = db.scalars(select(SpendRecord)).all()
        assert len(rows) == 2
        assert sum(r.cost_usd for r in rows) == pytest.approx(0.6)
        assert {r.problem_id for r in rows} == {"p0", "p1"}
        assert all(r.difficulty == "easy" and r.pricing["source"] == "override" for r in rows)
    # Workers materialize the same immutable input at a fresh local path.
    rematerialized = tmp_path / "resumed-input.json"
    rematerialized.write_bytes(data.read_bytes())
    runner.config.dataset_path = str(rematerialized)
    runner.run()
    with execution() as db:
        assert len(db.scalars(select(SpendRecord)).all()) == 2
    # Moving a file is safe, changing its content must still invalidate input.
    changed = json.loads(rematerialized.read_text(encoding="utf-8"))
    changed[0]["description"] = "A different description changes the frozen input."
    rematerialized.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="Checkpoint inputs changed"):
        runner.run()


def test_client_cache_zero_increment_and_storage_failure_does_not_retry_provider(
    execution, monkeypatch
):
    calls = []
    provider_client(monkeypatch, after_call=lambda: calls.append(1))
    client = LLMClient(config_model(cache=True))
    client.pricing_manager = pricing_snapshot(execution)
    client.on_response = SpendRecorder(execution, "ab_tests", "ab", "alice").callback(
        model="priced/model", strategy="vanilla"
    )
    client.generate("same prompt")
    client.generate("same prompt")
    with execution() as db:
        rows = db.scalars(select(SpendRecord)).all()
        assert len(rows) == 2
        assert sum(r.cost_usd for r in rows) == pytest.approx(0.3)
        assert sum(r.cached for r in rows) == 1

    def unavailable(*_):
        raise RuntimeError("accounting unavailable")

    client.on_response = unavailable
    with pytest.raises(RuntimeError, match="accounting unavailable"):
        client.generate("another prompt")
    assert len(calls) == 2


def test_provider_failure_records_unknown_instead_of_zero(execution, monkeypatch):
    provider_client(monkeypatch, fail=True)
    client = LLMClient(config_model())
    client.on_response = SpendRecorder(execution, "ab_tests", "ab", "alice").callback(
        model="priced/model", strategy="vanilla"
    )
    with pytest.raises(RuntimeError, match="provider stopped"):
        client.generate("prompt")
    with execution() as db:
        rows = db.scalars(select(SpendRecord)).all()
        assert len(rows) == 1
        assert rows[0].cost_usd is None
        assert rows[0].unknown_reason == "missing_response"


def test_persistence_failure_blocks_subsequent_provider_calls_and_marks_gap(execution, monkeypatch):
    calls = []
    provider_client(monkeypatch, after_call=lambda: calls.append(1))
    recorder = SpendRecorder(execution, "ab_tests", "ab", "alice")
    client = LLMClient(config_model())
    client.on_response = recorder.callback(model="priced/model", strategy="vanilla")
    client.before_generate = recorder.check

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(recorder, "record", fail_write)
    with pytest.raises(RuntimeError, match="database unavailable"):
        client.generate("first")
    with pytest.raises(RuntimeError, match="spend persistence"):
        client.generate("second")
    assert calls == [1]
    with execution() as db:
        assert db.get(ABTest, "ab").cost_tracking_complete is False


@pytest.mark.parametrize("kind", ["experiment", "ab"])
@pytest.mark.parametrize("ending", ["paused", "cancelled", "failed"])
def test_recorded_spend_survives_partial_runner_stop(
    execution, tmp_path, monkeypatch, kind, ending
):
    provider_client(monkeypatch)
    data = dataset(tmp_path, count=1 if kind == "experiment" else 2)
    if kind == "experiment":
        runner = ExperimentRunner(
            ExperimentConfig(
                dataset_path=str(data),
                output_dir=str(tmp_path / "results"),
                models=[config_model()],
                strategies=[StrategyConfig(name="vanilla")],
                repeats=2,
                sandbox_config=SandboxConfig(backend="host"),
            )
        )
        source, job, table = "experiments", "experiment", Experiment
        monkeypatch.setattr("src.experiment.generate_comparison_report", lambda _: None)
        monkeypatch.setattr("src.experiment.generate_html_panel", lambda _: None)
    else:
        runner = ABTestRunner(
            ABTestConfig(
                dataset_path=str(data),
                output_dir=str(tmp_path / "results"),
                model=config_model(),
                strategy=StrategyConfig(name="vanilla"),
                prompt_variants=[PromptVariant(id="a"), PromptVariant(id="b")],
                sandbox_config=SandboxConfig(backend="host"),
            )
        )
        source, job, table = "ab_tests", "ab", ABTest
    attach(runner, execution, source, job)
    original = runner.on_spend

    def record_and_stop(*args):
        original(*args)
        with execution() as db, db.begin():
            assert len(db.scalars(select(SpendRecord)).all()) == 1
            db.get(table, job).status = ending

    runner.on_spend = record_and_stop

    def stopped():
        with execution() as db:
            status = db.get(table, job).status
        if status == "failed":
            raise RuntimeError("interrupted after recorded call")
        return status in ("paused", "cancelled")

    if kind == "experiment":
        runner.should_pause = stopped
    else:
        runner.should_stop = stopped
    if ending == "failed":
        with pytest.raises(RuntimeError, match="interrupted after recorded call"):
            runner.run()
    else:
        runner.run()
    with execution() as db:
        rows = db.scalars(select(SpendRecord)).all()
        assert len(rows) == 1
        assert rows[0].cost_usd == pytest.approx(0.3)
        assert db.get(table, job).status == ending


def test_retried_timeout_keeps_unknown_attempt_alongside_success(execution, monkeypatch, tmp_path):
    from api.services.cost_service import CostService

    provider_client(monkeypatch)
    config = config_model().model_copy(update={"retry_max_attempts": 2, "retry_backoff_seconds": 0})
    client = LLMClient(config)
    client.pricing_manager = pricing_snapshot(execution)
    client.on_response = SpendRecorder(execution, "ab_tests", "ab", "alice").callback(
        model="priced/model", strategy="vanilla"
    )
    succeed = client.client.chat.completions.create
    attempts = []

    def retry(**kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("uncertain provider response")
        return succeed(**kwargs)

    client.client.chat.completions.create = retry
    client.generate("retry this prompt")
    with execution() as db:
        rows = db.scalars(select(SpendRecord)).all()
        assert len(rows) == 2
        assert sum(r.cost_usd or 0 for r in rows) == pytest.approx(0.3)
        assert sum(r.unknown_reason == "missing_response" for r in rows) == 1
    assert len(attempts) == 2
    service = CostService(f"sqlite:///{tmp_path}/spend.sqlite3")
    try:
        result = service.task_cost("ab", "alice")
        assert result["known_cost_usd"] == 0.3
        assert result["cost_complete"] is False
        assert result["unknown_cost_count"] == 1
    finally:
        service._engine.dispose()


def test_retry_accounting_failure_prevents_another_sdk_attempt(execution, monkeypatch):
    provider_client(monkeypatch)
    config = config_model().model_copy(update={"retry_max_attempts": 2, "retry_backoff_seconds": 0})
    client = LLMClient(config)
    attempts = []

    def timeout(**_):
        attempts.append(1)
        raise TimeoutError("uncertain provider response")

    client.client.chat.completions.create = timeout
    recorder = SpendRecorder(execution, "ab_tests", "ab", "alice")

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(recorder, "record", fail_write)
    client.on_response = recorder.callback(model="priced/model", strategy="vanilla")
    with pytest.raises(RuntimeError, match="spend persistence"):
        client.generate("retry accounting")
    assert len(attempts) == 1
