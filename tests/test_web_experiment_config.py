"""Issue #526: saved Web configuration reaches real offline execution."""

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.config import settings
from api.db.models import Experiment
from src.experiment import ExperimentRunner
from src.models import LLMConfig, Problem, SandboxResult
from tests.test_api_experiment_benchmark import (  # noqa: F401
    api,
    celery_submit,
    shared_results_root,
)


@pytest.mark.parametrize("stop", [None, "max_calls", "max_tokens", "max_seconds"])
def test_saved_web_config_controls_real_strategy_filters_and_budget(
    api, tmp_path, monkeypatch, stop  # noqa: F811
):
    client, headers, key_id, app = api
    monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
    questions = []
    for identity, difficulty, tag in [
        ("hard", "hard", "array"),
        ("wrong-tag", "easy", "graph"),
        ("excluded-id", "easy", "array"),
        ("picked-a", "easy", "array"),
        ("picked-b", "easy", "math"),
        ("picked-c", "easy", "array"),
    ]:
        questions.append(
            Problem(
                problem_id=identity,
                title=identity,
                description="Return the integer one.",
                difficulty=difficulty,
                tags=[tag],
                public_test_cases=[{"input": {"x": 1}, "expected_output": 1}],
            ).model_dump(mode="json")
        )
    (tmp_path / "questions.json").write_text(json.dumps(questions), encoding="utf-8")
    filters = {
        "difficulty": "easy",
        "tags": ["array", "math"],
        "problem_ids": [q["problem_id"] for q in questions if q["problem_id"] != "excluded-id"],
        "limit": 2,
    }
    strategy = {
        "name": "self_consistency",
        "max_tokens": 3456,
        "system_prompt": "Use the supplied instructions.",
        "custom_params": {"num_candidates": 3, "temperature": 1.2},
    }
    budget = {"max_calls": 10, "max_tokens": 1000, "max_seconds": 100.0}
    if stop:
        budget[stop] = {"max_calls": 1, "max_tokens": 15, "max_seconds": 0.1}[stop]
    payload = {
        "name": "web-advanced",
        "dataset_path": "questions.json",
        "api_key_id": key_id,
        "models": [{"model": "offline"}],
        "strategies": [strategy],
        "problem_filters": filters,
        "budget": budget,
    }
    response = client.post("/api/v1/experiments", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    identity = response.json()["data"]["id"]
    service = app.state.experiments
    with service._session() as session:
        row = session.get(Experiment, identity)
        owner = row.user_id
        stored = row.config
    assert stored["problem_filters"] == filters
    assert stored["budget"] == budget
    assert stored["strategies"][0]["custom_params"] == strategy["custom_params"]
    assert "temperature" not in stored["strategies"][0]
    model = LLMConfig(
        provider="openai", model="offline", api_key="mock-key", cache={"enabled": False}
    )
    clock = [0.0]
    # Replace only budget's clock, keeping application/test time untouched.
    monkeypatch.setattr("src.budget.time", SimpleNamespace(monotonic=lambda: clock[0]))
    with (
        ExitStack() as files,
        patch.object(service._auth, "llm_config", return_value=model),
        patch("src.llm_client.OpenAI") as sdk,
        patch("src.harness.SandboxExecutor") as sandbox,
    ):
        sandbox.return_value.health_check.return_value = (True, "offline mock")
        sandbox.return_value.execute.return_value = SandboxResult(status="success", all_passed=True)

        def generate(**kwargs):
            clock[0] += 0.2
            return SimpleNamespace(
                model="offline",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="```python\ndef solution(x): return 1\n```"
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        sdk.return_value.chat.completions.create.side_effect = generate
        config = service._build_runner_config(row, owner, files)
        assert config.problem_filters == filters
        assert config.budget.model_dump() == budget
        assert config.strategies[0].custom_params == strategy["custom_params"]
        output = ExperimentRunner(config).run()
        calls = sdk.return_value.chat.completions.create.call_args_list
    metadata = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    assert metadata["dataset"]["problem_ids"] == ["picked-a", "picked-b"]
    combo = next(output.glob("combo-*"))
    ledger = json.loads((combo / "budget_ledger.json").read_text(encoding="utf-8"))
    assert ledger["budget"] == budget
    assert [entry["problem_id"] for entry in ledger["problems"]] == ["picked-a", "picked-b"]
    per_problem = 1 if stop else 3
    assert [entry["calls"] for entry in ledger["problems"]] == [per_problem] * 2
    assert [entry["stop_reason"] for entry in ledger["problems"]] == [
        f"budget_exhausted: {stop}" if stop else "completed"
    ] * 2
    assert len(calls) == per_problem * 2
    for call in calls:
        assert call.kwargs["max_tokens"] == 3456
        assert call.kwargs["temperature"] == 1.2
        assert call.kwargs["messages"][0] == {
            "role": "system",
            "content": strategy["system_prompt"],
        }
        assert "num_candidates" not in call.kwargs
    detail = client.get(f"/api/v1/experiments/{identity}", headers=headers).json()["data"]
    assert detail["config"]["problem_filters"] == filters
    assert detail["config"]["strategies"] == stored["strategies"]
