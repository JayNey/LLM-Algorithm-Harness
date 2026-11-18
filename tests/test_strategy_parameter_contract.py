"""Issue #492: persisted overrides and production ToT configuration."""

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from api.db.models import ABTest, BenchmarkRun, Experiment
from src.ab_testing import ABTestConfig
from src.checkpoints import UnitCheckpoint
from src.harness import AlgorithmHarness
from src.llm_client import LLMClient
from src.models import ExperimentConfig, HarnessConfig, LLMConfig, StrategyConfig
from src.strategies.tree_of_thoughts import TreeOfThoughtsStrategy
from src.strategies.vanilla import VanillaStrategy
from src.task_service import TaskService
from tests.test_api_experiment_benchmark import (  # noqa: F401
    FakeBenchmarkExecutor,
    _experiment_payload,
    api,
    celery_submit,
    shared_results_root,
)
from tests.test_api_experiment_benchmark import TestABTests as _ABTests


def model():
    return LLMConfig(
        provider="openai",
        model="test",
        api_key="offline-key",
        temperature=0.2,
        max_tokens=3500,
        cache={"enabled": False},
    )


def sdk_response(text="answer"):
    return SimpleNamespace(
        model="test",
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def check_generation(strategy_config, llm_config, temperature, max_tokens):
    # Real parameter resolution and request construction, only transport is replaced.
    with patch("src.llm_client.OpenAI") as sdk:
        sdk.return_value.chat.completions.create.return_value = sdk_response()
        client = LLMClient(llm_config)
        response = VanillaStrategy(strategy_config, client, Mock()).generate("solve")
        request = sdk.return_value.chat.completions.create.call_args.kwargs
    assert request["temperature"] == temperature
    assert request["max_tokens"] == max_tokens
    assert response.effective_params["temperature"] == temperature
    assert response.effective_params["max_tokens"] == max_tokens


@pytest.mark.parametrize("business", ["experiment", "ab", "benchmark"])
@pytest.mark.parametrize(
    "overrides,temperature,max_tokens",
    [
        ({}, 0.2, 3500),
        ({"temperature": 0.7}, 0.7, 3500),
        ({"max_tokens": 2000}, 0.2, 2000),
        ({"temperature": 0.7, "max_tokens": 2000}, 0.7, 2000),
    ],
)
def test_database_round_trip_preserves_generation_overrides(
    api,  # noqa: F811 - imported pytest fixture
    business,
    overrides,
    temperature,
    max_tokens,
):
    client, headers, key_id, app = api
    strategy = {"name": "vanilla", **overrides}
    if business == "experiment":
        payload = _experiment_payload(key_id)
        payload["strategies"] = [strategy]
        payload["models"][0]["temperature"] = 0.2
        created = client.post("/api/v1/experiments", headers=headers, json=payload)
        service, row_type = app.state.experiments, Experiment
    elif business == "ab":
        payload = _ABTests()._ab_payload(key_id)
        payload["strategy"] = strategy
        payload["model"]["temperature"] = 0.2
        created = client.post("/api/v1/ab-tests", headers=headers, json=payload)
        service, row_type = app.state.ab_tests, ABTest
    else:
        suite = client.post(
            "/api/v1/benchmarks/suites",
            headers=headers,
            json={"name": "parameters", "problems": ["two-sum"]},
        )
        suite_id = suite.json()["data"]["id"]
        created = client.post(
            f"/api/v1/benchmarks/suites/{suite_id}/run",
            headers=headers,
            json={
                "api_key_id": key_id,
                "dataset_path": "problems.json",
                "model": "test",
                "strategies": [strategy],
            },
        )
        service, row_type = app.state.benchmarks, BenchmarkRun
    assert created.status_code in (201, 202), created.text
    with service._session() as session:
        row = session.get(row_type, created.json()["data"]["id"])
        owner = row.user_id
        stored = row.config["strategy"] if business == "ab" else row.config["strategies"][0]
    assert ("temperature" in stored) == ("temperature" in overrides)
    assert ("max_tokens" in stored) == ("max_tokens" in overrides)
    with patch.object(service._auth, "llm_config", return_value=model()), ExitStack() as files:
        if business == "experiment":
            config = service._build_runner_config(row, owner, files)
            loaded, llm = config.strategies[0], config.models[0]
        elif business == "ab":
            config = service._build_config(row, owner, files)
            loaded, llm = config.strategy, config.model
        else:
            service._execute(row.id, owner)
            config = FakeBenchmarkExecutor.last_config
            loaded, llm = config.strategies[0], config.llm_config
    check_generation(loaded, llm, temperature, max_tokens)


@pytest.mark.parametrize("kind", ["strategy", "harness", "experiment", "ab"])
def test_nested_config_snapshots_keep_omitted_overrides(kind):
    strategy = StrategyConfig(name="vanilla")
    if kind == "strategy":
        config = strategy
    elif kind == "harness":
        config = HarnessConfig(dataset_path="unused", llm_config=model(), strategies=[strategy])
    elif kind == "experiment":
        config = ExperimentConfig(dataset_path="unused", models=[model()], strategies=[strategy])
    else:
        config = ABTestConfig(
            dataset_path="unused",
            model=model(),
            strategy=strategy,
            prompt_variants=[{"id": "a"}, {"id": "b"}],
        )
    restored = type(config).model_validate_json(config.model_dump_json())
    loaded = (
        restored
        if kind == "strategy"
        else restored.strategy if kind == "ab" else restored.strategies[0]
    )
    check_generation(loaded, model(), 0.2, 3500)


def test_historical_explicit_defaults_remain_overrides():
    stored = {"name": "vanilla", "temperature": 0.7, "max_tokens": 2000}
    restored = StrategyConfig.model_validate_json(json.dumps(stored))
    check_generation(restored, model(), 0.7, 2000)


def factory(custom_params):
    strategy = StrategyConfig(name="tree_of_thoughts", custom_params=custom_params)
    harness = AlgorithmHarness(
        HarnessConfig(dataset_path="unused", llm_config=model(), strategies=[strategy])
    )
    with patch("src.harness.SandboxExecutor") as sandbox:
        sandbox.return_value.health_check.return_value = (True, "ok")
        instance, _ = harness._prepare_strategy_runtime(strategy)
    return instance


CONTROLS = {
    "branching_factor": 1,
    "max_depth": 1,
    "search_strategy": "dfs",
    "pruning_threshold": 0.9,
}


def test_harness_tot_controls_reach_search_and_stay_out_of_sdk(sample_problem):
    with patch("src.llm_client.OpenAI") as sdk:
        transport = sdk.return_value.chat.completions.create
        transport.side_effect = [
            sdk_response(
                "=== Approach 1 ===\nReasoning: identity\nCode:\n```python\ndef solution(x): return x\n```"
            ),
            sdk_response("0.8"),
        ]
        strategy = factory({**CONTROLS, "top_p": 0.85})
        assert (
            strategy.branching_factor,
            strategy.max_depth,
            strategy.search_strategy,
            strategy.pruning_threshold,
        ) == (1, 1, "dfs", 0.9)
        result = strategy.execute(sample_problem)
    # One generated branch, one scoring call; score 0.8 is pruned at 0.9.
    assert transport.call_count == 2
    assert result.generated_code == ""
    assert result.status != "success"
    assert len(result.iterations) == 2
    for call in transport.call_args_list:
        assert not CONTROLS.keys() & call.kwargs.keys()
        assert call.kwargs["top_p"] == 0.85
    for iteration in result.iterations:
        assert not CONTROLS.keys() & iteration.effective_params.keys()
        assert iteration.effective_params["top_p"] == 0.85


@pytest.mark.parametrize(
    "field,value",
    [
        ("branching_factor", 0),
        ("branching_factor", True),
        ("branching_factor", 1.5),
        ("max_depth", 0),
        ("max_depth", False),
        ("max_depth", "1"),
        ("search_strategy", "invalid"),
        ("search_strategy", []),
        ("pruning_threshold", -0.1),
        ("pruning_threshold", 1.1),
        ("pruning_threshold", True),
        ("pruning_threshold", "0.9"),
        ("pruning_threshold", float("nan")),
        ("pruning_threshold", float("inf")),
    ],
)
def test_harness_rejects_invalid_tot_before_provider_call(field, value):
    with patch("src.llm_client.OpenAI") as sdk:
        with pytest.raises(ValueError, match=field):
            factory({field: value})
    sdk.return_value.chat.completions.create.assert_not_called()


def test_tot_defaults_and_explicit_constructor_precedence():
    with patch("src.llm_client.OpenAI"):
        default = factory({})
    assert (
        default.branching_factor,
        default.max_depth,
        default.search_strategy,
        default.pruning_threshold,
    ) == (3, 4, "bfs", 0.3)
    explicit = TreeOfThoughtsStrategy(
        StrategyConfig(name="tree_of_thoughts", custom_params=CONTROLS),
        Mock(),
        Mock(),
        branching_factor=3,
        max_depth=4,
        search_strategy="bfs",
        pruning_threshold=0.3,
    )
    assert (
        explicit.branching_factor,
        explicit.max_depth,
        explicit.search_strategy,
        explicit.pruning_threshold,
    ) == (3, 4, "bfs", 0.3)


@pytest.mark.parametrize("field,value", [("temperature", 0.7), ("max_tokens", 2000)])
def test_checkpoint_refuses_omitted_vs_explicit_defaults(tmp_path, field, value):
    config = HarnessConfig(
        dataset_path="unused", llm_config=model(), strategies=[{"name": "vanilla"}]
    )
    changed = config.model_copy(deep=True)
    setattr(changed.strategies[0], field, value)
    checkpoint = UnitCheckpoint(tmp_path, TaskService.config_fingerprint(config))
    checkpoint.put("unit", {"status": "success"})
    with pytest.raises(ValueError, match="Checkpoint inputs changed"):
        UnitCheckpoint(tmp_path, TaskService.config_fingerprint(changed))
    assert checkpoint.get("unit") == {"status": "success"}


def test_checkpoint_refuses_old_parameter_contract_and_search_changes(tmp_path):
    snapshot = {"strategy": {"name": "tree_of_thoughts", "custom_params": CONTROLS}}
    # Pre-fix config_fingerprint hashed the redacted snapshot directly.
    old = TaskService._hash_json(snapshot)
    checkpoint = UnitCheckpoint(tmp_path / "old", old)
    checkpoint.put("unit", {"status": "success"})
    with pytest.raises(ValueError, match="Checkpoint inputs changed"):
        UnitCheckpoint(tmp_path / "old", TaskService.config_fingerprint(snapshot))
    assert checkpoint.get("unit") == {"status": "success"}
    current = UnitCheckpoint(tmp_path / "current", TaskService.config_fingerprint(snapshot))
    changed = {"strategy": {"name": "tree_of_thoughts", "custom_params": {"max_depth": 2}}}
    with pytest.raises(ValueError, match="Checkpoint inputs changed"):
        UnitCheckpoint(current.root, TaskService.config_fingerprint(changed))
