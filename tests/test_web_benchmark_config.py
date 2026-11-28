"""Issue #528: Web benchmark parameters reach real offline execution."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.config import settings
from api.db.models import BenchmarkRun
from src.benchmark.executor import BenchmarkExecutor
from src.benchmark.suite import BenchmarkSuite
from src.models import HarnessConfig, LLMConfig, Problem, SandboxResult
from tests.test_api_experiment_benchmark import (  # noqa: F401
    _execute_benchmark,
    api,
    celery_submit,
    shared_results_root,
)


def questions(tmp_path):
    data = [
        Problem(
            problem_id=identity,
            title=identity,
            description="Return the integer one.",
            difficulty=difficulty,
            tags=[tag],
            public_test_cases=[{"input": {"x": 1}, "expected_output": 1}],
        ).model_dump(mode="json")
        for identity, difficulty, tag in [
            ("outside", "easy", "array"),
            ("a", "easy", "array"),
            ("b", "easy", "math"),
            ("wrong-tag", "easy", "graph"),
            ("hard", "hard", "array"),
            ("excluded", "easy", "array"),
        ]
    ]
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_saved_config_controls_real_execution_and_history(api, tmp_path, monkeypatch):  # noqa: F811
    client, headers, key, app = api
    monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
    questions(tmp_path)
    service = app.state.benchmarks
    captured = []

    def executor(suite, config):
        captured.append(config)
        return BenchmarkExecutor(suite, config)

    monkeypatch.setattr(service, "_executor_factory", executor)
    suite = client.post(
        "/api/v1/benchmarks/suites",
        headers=headers,
        json={
            "name": "advanced",
            "problems": ["hard", "wrong-tag", "excluded", "b", "a"],
            "frozen": True,
        },
    ).json()["data"]
    filters = {
        "difficulty": "easy",
        "tags": ["array", "math"],
        "problem_ids": ["outside", "hard", "wrong-tag", "a", "b"],
        "limit": 1,
    }
    strategy = {
        "name": "self_consistency",
        "max_iterations": 3,
        "temperature": 0,
        "max_tokens": 3456,
        "system_prompt": "Follow these instructions.",
        "custom_params": {"num_candidates": 3, "temperature": 1.2},
    }
    started = client.post(
        f"/api/v1/benchmarks/suites/{suite['id']}/run",
        headers=headers,
        json={
            "api_key_id": key,
            "dataset_path": "questions.json",
            "model": "offline",
            "strategies": [strategy],
            "problem_filters": filters,
        },
    )
    assert started.status_code == 202, started.text
    identity = started.json()["data"]["id"]
    with service._session() as session:
        stored = session.get(BenchmarkRun, identity).config
    assert stored["problem_filters"] == filters
    assert stored["strategies"] == [strategy]
    model = LLMConfig(provider="openai", model="offline", api_key="mock", cache={"enabled": False})
    with (
        patch.object(service._auth, "llm_config", return_value=model),
        patch("src.llm_client.OpenAI") as sdk,
        patch("src.harness.SandboxExecutor") as sandbox,
    ):
        sandbox.return_value.health_check.return_value = (True, "offline")
        sandbox.return_value.execute.return_value = SandboxResult(status="success", all_passed=True)
        sdk.return_value.chat.completions.create.return_value = SimpleNamespace(
            model="offline",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="```python\ndef solution(x): return 1\n```"),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        _execute_benchmark(app, identity)
        calls = sdk.return_value.chat.completions.create.call_args_list
    assert len(calls) == 3
    for call in calls:
        assert call.kwargs["max_tokens"] == 3456
        assert call.kwargs["temperature"] == 1.2
        assert call.kwargs["messages"][0] == {
            "role": "system",
            "content": strategy["system_prompt"],
        }
    assert captured[0].strategies[0].model_dump() == strategy
    assert captured[0].problem_filters == filters
    detail = client.get(f"/api/v1/benchmarks/runs/{identity}", headers=headers).json()["data"]
    assert detail["status"] == "completed", detail
    assert detail["results"]["problems_evaluated"] == 1
    assert detail["results"]["strategies"]["self_consistency"]["total"] == 1
    assert detail["accuracy"] == 1.0
    assert detail["cost_usd"] >= 0
    # Persisted execution units prove the selected ID, including suite order before limit.
    files = list((Path("results/benchmarks/api") / identity / "units").rglob("*.json"))
    assert files
    assert any('"b"' in f.read_text(encoding="utf-8") for f in files)
    assert not any('"a"' in f.read_text(encoding="utf-8") for f in files)
    history = client.get(f"/api/v1/benchmarks/suites/{suite['id']}/runs", headers=headers).json()[
        "data"
    ]
    assert history["items"][0]["id"] == identity
    assert history["items"][0]["accuracy"] == 1.0
    assert (
        client.get(f"/api/v1/benchmarks/suites/{suite['id']}", headers=headers).json()["data"]
        == suite
    )


@pytest.mark.parametrize(
    "filters,crash", [(None, False), ({"limit": 1}, True), ({"tags": ["none"]}, False)]
)
def test_executor_compatibility_empty_and_cleanup(tmp_path, filters, crash):
    config = HarnessConfig(
        dataset_path=str(questions(tmp_path)),
        problem_filters=filters,
        llm_config=LLMConfig(provider="openai", model="offline", api_key="mock"),
        strategies=[{"name": "vanilla"}],
    )
    before = config.model_dump()
    suite = BenchmarkSuite(name="fixed", problems=["b", "a"])
    with patch("src.benchmark.executor.AlgorithmHarness") as harness:
        if filters == {"tags": ["none"]}:
            with pytest.raises(ValueError, match="No benchmark suite problems match"):
                BenchmarkExecutor(suite, config).execute()
            harness.assert_not_called()
        else:
            if crash:
                harness.return_value.run.side_effect = RuntimeError("offline failure")
                with pytest.raises(RuntimeError, match="offline failure"):
                    BenchmarkExecutor(suite, config).execute()
            else:
                harness.return_value.run.return_value = {}
                result = BenchmarkExecutor(suite, config).execute()
                assert result["problems_evaluated"] == 2
            transient = harness.call_args.args[0]
            assert transient.problem_filters is None
            assert not Path(transient.dataset_path).exists()
    assert config.model_dump() == before
