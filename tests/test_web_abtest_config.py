"""Issue #527: Web A/B settings reach actual strategies and filtered execution."""

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.config import settings
from api.db.models import ABTest
from src.ab_testing import ABTestRunner, stratified_assign
from src.models import LLMConfig, Problem, SandboxResult
from tests.test_api_experiment_benchmark import (  # noqa: F401
    api,
    celery_submit,
    shared_results_root,
)


@pytest.mark.parametrize("mode", ["vanilla", "inherited", "self_consistency", "too-few"])
def test_saved_web_abtest_config_controls_real_execution(
    api, tmp_path, monkeypatch, mode  # noqa: F811
):
    client, headers, key_id, app = api
    monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
    questions = [
        Problem(
            problem_id=identity,
            title=identity,
            description="Return the integer one.",
            difficulty=difficulty,
            tags=[tag],
            public_test_cases=[{"input": {"x": 1}, "expected_output": 1}],
        )
        for identity, difficulty, tag in [
            ("hard", "hard", "array"),
            ("wrong-tag", "easy", "graph"),
            ("excluded-id", "easy", "array"),
            ("picked-a", "easy", "array"),
            ("picked-b", "easy", "math"),
            ("picked-c", "easy", "array"),
        ]
    ]
    (tmp_path / "questions.json").write_text(
        json.dumps([q.model_dump(mode="json") for q in questions]), encoding="utf-8"
    )
    filters = {
        "difficulty": "easy",
        "tags": ["array", "math"],
        "problem_ids": [q.problem_id for q in questions if q.problem_id != "excluded-id"],
        "limit": 1 if mode == "too-few" else 2,
    }
    strategy = {
        "name": "self_consistency" if mode == "self_consistency" else "vanilla",
        "system_prompt": "strategy default",
    }
    if mode != "inherited":
        strategy.update(temperature=0.25, max_tokens=3456)
    if mode == "self_consistency":
        strategy["custom_params"] = {"num_candidates": 3, "temperature": 1.2}
    payload = {
        "name": "web-ab-advanced",
        "dataset_path": "questions.json",
        "api_key_id": key_id,
        "model": {"model": "offline", "temperature": 0.4},
        "strategy": strategy,
        "problem_filters": filters,
        "baseline_id": "control",
        "seed": 17,
        "max_workers": 2,
        "prompt_variants": [
            {"id": "control", "prefix": "CONTROL:", "suffix": ":END"},
            {"id": "experiment", "system_prompt": "variant override", "prefix": "VARIANT:"},
        ],
    }
    response = client.post("/api/v1/ab-tests", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    identity = response.json()["data"]["id"]
    service = app.state.ab_tests
    with service._session() as session:
        row = session.get(ABTest, identity)
        owner, stored = row.user_id, row.config
    assert stored["problem_filters"] == filters
    assert stored["prompt_variants"][1]["system_prompt"] == "variant override"
    assert stored["strategy"]["custom_params"] == strategy.get("custom_params", {})
    if mode == "inherited":
        assert "temperature" not in stored["strategy"] and "max_tokens" not in stored["strategy"]
    model = LLMConfig(
        provider="openai",
        model="offline",
        api_key="mock-key",
        temperature=0.9,
        max_tokens=4567,
        cache={"enabled": False},
    )
    with (
        ExitStack() as files,
        patch.object(service._auth, "llm_config", return_value=model),
        patch("src.llm_client.OpenAI") as sdk,
    ):
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
        config = service._build_config(row, owner, files)
        assert config.problem_filters == filters
        assert (config.seed, config.max_workers, config.baseline.id) == (17, 2, "control")
        sandbox = SimpleNamespace(
            health_check=lambda: (True, "offline mock"),
            execute=lambda *args, **kwargs: SandboxResult(status="success", all_passed=True),
        )
        runner = ABTestRunner(config, sandbox_factory=lambda _: sandbox)
        if mode == "too-few":
            with pytest.raises(ValueError, match="at least one problem in each variant"):
                runner.run()
            sdk.return_value.chat.completions.create.assert_not_called()
            return
        output = runner.run()
        calls = sdk.return_value.chat.completions.create.call_args_list
    report = json.loads((output / "ab_test.json").read_text(encoding="utf-8"))
    assert set(report["assignments"]) == {"picked-a", "picked-b"}
    picked = [q for q in questions if q.problem_id in {"picked-a", "picked-b"}]
    assert {
        key: value["variant"] for key, value in report["assignments"].items()
    } == stratified_assign(picked, config.prompt_variants, 17)
    assert report["baseline_id"] == "control"
    assert len(report["rows"]) == 2
    assert all(row["sample_passed"] for row in report["rows"])
    per_problem = 3 if mode == "self_consistency" else 1
    assert len(calls) == per_problem * 2
    seen_systems = []
    for call in calls:
        kwargs = call.kwargs
        assert kwargs["max_tokens"] == (4567 if mode == "inherited" else 3456)
        assert (
            kwargs["temperature"]
            == {"inherited": 0.4, "vanilla": 0.25, "self_consistency": 1.2}[mode]
        )
        messages = kwargs["messages"]
        prompt = messages[-1]["content"]
        assert "hard" not in prompt and "wrong-tag" not in prompt and "excluded-id" not in prompt
        if prompt.startswith("CONTROL:"):
            assert prompt.endswith(":END")
            assert messages[0]["content"] == "strategy default"
        else:
            assert prompt.startswith("VARIANT:")
            assert messages[0]["content"] == "variant override"
        seen_systems.append(messages[0]["content"])
        assert "num_candidates" not in kwargs
    assert seen_systems.count("strategy default") == per_problem
    assert seen_systems.count("variant override") == per_problem
    detail = client.get(f"/api/v1/ab-tests/{identity}", headers=headers).json()["data"]
    assert detail["config"]["strategy"] == stored["strategy"]
    assert detail["config"]["problem_filters"] == filters
