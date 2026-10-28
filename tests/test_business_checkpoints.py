"""Completed units survive normal pause/resume without a second model call."""

import io
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from api.auth.store import AuthStore
from api.files.config import FileSettings
from api.files.service import FileService
from src.ab_testing import ABTestConfig, ABTestRunner
from src.benchmark.executor import BenchmarkExecutor
from src.benchmark.suite import BenchmarkSuite
from src.experiment import ExperimentRunner
from src.harness import AlgorithmHarness
from src.models import ExecutionResult, ExperimentConfig, HarnessConfig, LLMConfig, SandboxConfig


@pytest.fixture
def dataset(tmp_path):
    data = [
        {
            "problem_id": f"p{i}",
            "title": f"Problem {i}",
            "description": "Return the provided integer unchanged.",
            "difficulty": "easy",
            "tags": [],
            "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
        }
        for i in range(4)
    ]
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def llm():
    return LLMConfig(provider="openai", model="test", api_key="test-secret")


def test_experiment_resumes_same_directory_and_skips_saved_combinations(tmp_path, dataset):
    config = ExperimentConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        models=[llm()],
        strategies=[{"name": "vanilla"}],
        repeats=3,
    )
    calls = []

    def combo(self, output, model, strategy, repeat):
        calls.append(repeat)
        return {
            "combo_id": f"combo-{repeat}",
            "model": model.model,
            "strategy": strategy.name,
            "repeat": repeat,
            "combo_dir": f"combo-{repeat}",
        }

    def runner():
        value = ExperimentRunner(config)
        value.checkpoint_dir = tmp_path / "execution"
        return value

    with (
        patch.object(ExperimentRunner, "_run_combo", combo),
        patch("src.experiment.generate_comparison_report"),
        patch("src.experiment.generate_html_panel"),
    ):
        first = runner()
        first.should_pause = lambda: len(calls) == 1
        output = first.run()
        assert first.paused
        second = runner()
        assert second.run() == output
    assert calls == [1, 2, 3]
    saved = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    assert len(saved["combinations"]) == 3


def test_benchmark_resume_preserves_results_tokens_and_cost(tmp_path, dataset):
    config = HarnessConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        llm_config=llm(),
        strategies=[{"name": "vanilla"}],
    )
    suite = BenchmarkSuite(name="fixed", problems=["p0", "p1", "p2", "p3"])
    calls = []

    def execute(self, strategy, problem, *args):
        calls.append(problem.problem_id)
        return ExecutionResult(
            problem_id=problem.problem_id,
            strategy="vanilla",
            generated_code="",
            status="success",
            total_tokens=10,
            llm_traces=[
                {"total_tokens": 10, "pricing_metadata": {"total_cost": 0.25, "model": "test"}}
            ],
        )

    def executor():
        value = BenchmarkExecutor(suite, config)
        value.checkpoint_dir = tmp_path / "units"
        return value

    with (
        patch.object(
            AlgorithmHarness, "_prepare_strategy_runtime", return_value=(object(), object())
        ),
        patch.object(AlgorithmHarness, "_execute_problem", execute),
    ):
        first = executor()
        first.should_pause = lambda: len(calls) == 1
        first.execute()
        assert first.paused
        result = executor().execute()
    assert calls == ["p0", "p1", "p2", "p3"]
    assert result["strategies"]["vanilla"]["total_tokens"] == 40
    assert result["cost_usd"] == 1.0
    assert result["accuracy"] == 1.0


def test_ab_resume_keeps_assignment_and_completed_problem_rows(tmp_path, dataset):
    config = ABTestConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        model=llm(),
        strategy={"name": "vanilla"},
        prompt_variants=[{"id": "a"}, {"id": "b"}],
        sandbox_config=SandboxConfig(backend="host"),
    )
    calls = []

    def execute(self, strategy, problem, *args):
        calls.append(problem.problem_id)
        return ExecutionResult(
            problem_id=problem.problem_id,
            strategy="vanilla",
            generated_code="",
            status="success",
            total_tokens=10,
        )

    def runner():
        value = ABTestRunner(
            config,
            client_factory=lambda cfg: SimpleNamespace(config=cfg),
            sandbox_factory=lambda _: SimpleNamespace(health_check=lambda: (True, "ok")),
        )
        value.checkpoint_dir = tmp_path / "execution"
        return value

    with patch.object(AlgorithmHarness, "_execute_problem", execute):
        first = runner()
        first.should_stop = lambda: len(calls) == 1
        output = first.run()
        assert runner().run() == output
    assert len(calls) == len(set(calls)) == 4
    report = json.loads((output / "ab_test.json").read_text(encoding="utf-8"))
    assert len(report["rows"]) == 4
    assert sum(report["comparison"]["tokens"].values()) == 40


def test_import_resume_skips_validated_rows_and_merges_once(tmp_path, dataset):
    auth = SimpleNamespace(store=AuthStore(tmp_path / "auth.db"), audit=Mock())
    service = FileService(auth, FileSettings(UPLOAD_DIR=tmp_path / "uploads"))
    record = service.upload(
        io.BytesIO(dataset.read_bytes()), "data.json", "application/json", "owner"
    )
    job = service.store.create_job(record["file"]["id"], "owner", "append")
    from api.files.parsing import validate_problem

    validated = []

    def validate(item, csv_source=False):
        validated.append(item["problem_id"])
        return validate_problem(item, csv_source)

    with patch("api.files.service.validate_problem", side_effect=validate):
        service.process_job(job, "owner", should_pause=lambda: len(validated) == 1)
        paused = service.store.job(job, "owner")
        assert paused["status"] == "paused"
        assert paused["processed"] == 1
        assert service.store.dataset("owner") == []
        service.store.sync_task_status(job, "owner", "pending")
        service.process_job(job, "owner")
    assert validated == ["p0", "p1", "p2", "p3"]
    assert service.store.job(job, "owner")["result"]["imported"] == 4
    assert len(service.store.dataset("owner")) == 4


def test_same_named_experiment_model_arms_remain_distinct_on_resume(tmp_path, dataset):
    config = ExperimentConfig(
        dataset_path=str(dataset),
        models=[
            llm().model_copy(update={"temperature": 0.1}),
            llm().model_copy(update={"temperature": 0.9}),
        ],
        strategies=[{"name": "vanilla"}],
    )
    calls = []

    def combo(self, output, model, strategy, repeat):
        calls.append(model.temperature)
        return {
            "combo_id": "combo",
            "combo_dir": "combo",
            "model": model.model,
            "strategy": strategy.name,
            "repeat": repeat,
        }

    with (
        patch.object(ExperimentRunner, "_run_combo", combo),
        patch("src.experiment.generate_comparison_report"),
        patch("src.experiment.generate_html_panel"),
    ):
        first = ExperimentRunner(config)
        first.checkpoint_dir = tmp_path / "execution"
        first.should_pause = lambda: len(calls) == 1
        first.run()
        second = ExperimentRunner(config)
        second.checkpoint_dir = first.checkpoint_dir
        second.run()
    assert calls == [0.1, 0.9]


def test_ab_single_result_per_arm_has_json_safe_statistics():
    from src.ab_testing import _statistical_tests

    stats = _statistical_tests([1], [0])
    assert stats["welch_t_p_value"] is None


def test_parallel_experiment_does_not_start_queued_combinations_after_pause(tmp_path, dataset):
    config = ExperimentConfig(
        dataset_path=str(dataset),
        models=[llm()],
        strategies=[{"name": "vanilla"}],
        repeats=4,
        execution="parallel",
        max_workers=1,
    )
    submitted = threading.Event()
    reported = []
    calls = []
    runner = ExperimentRunner(config)
    runner.checkpoint_dir = tmp_path / "execution"

    def report(*args):
        reported.append(1)
        if len(reported) == 4:
            submitted.set()

    def combo(self, output, model, strategy, repeat):
        assert submitted.wait(2)
        calls.append(repeat)
        return {
            "combo_id": "one",
            "combo_dir": "one",
            "model": model.model,
            "strategy": strategy.name,
            "repeat": repeat,
        }

    runner.on_combination = report
    runner.should_pause = lambda: bool(calls)
    with patch.object(ExperimentRunner, "_run_combo", combo):
        runner.run()
    assert runner.paused
    assert calls == [1]


def test_benchmark_checkpoint_distinguishes_strategy_parameters(tmp_path, dataset):
    config = HarnessConfig(
        dataset_path=str(dataset),
        llm_config=llm(),
        strategies=[
            {"name": "vanilla", "max_iterations": 1},
            {"name": "vanilla", "max_iterations": 2},
        ],
    )
    executor = BenchmarkExecutor(BenchmarkSuite(name="fixed", problems=["p0"]), config)
    executor.checkpoint_dir = tmp_path / "units"
    calls = []

    def execute(self, strategy, problem, *args):
        calls.append(strategy.max_iterations)
        return ExecutionResult(
            problem_id=problem.problem_id, strategy="vanilla", generated_code="", status="success"
        )

    with (
        patch.object(
            AlgorithmHarness, "_prepare_strategy_runtime", return_value=(object(), object())
        ),
        patch.object(AlgorithmHarness, "_execute_problem", execute),
    ):
        executor.execute()
    assert calls == [1, 2]
