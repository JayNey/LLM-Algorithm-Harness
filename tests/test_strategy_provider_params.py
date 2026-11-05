"""Real SDK boundaries: strategy controls must never become provider kwargs."""

import json
from unittest.mock import Mock

import httpx
import pytest
from anthropic import Anthropic
from anthropic import _base_client as anthropic_transport
from openai import OpenAI

from src.cache import LLMResponseCache
from src.code_quality.models import CodeQualityMetrics  # noqa: F401
from src.llm_client import LLMClient
from src.models import CacheConfig, ExecutionResult, LLMConfig, SandboxResult, StrategyConfig
from src.strategies.few_shot_learning import (
    ExampleProblem,
    FewShotLearningStrategy,
    SimilarProblem,
)
from src.strategies.reflexion import ReflexionStrategy
from src.strategies.self_consistency import SelfConsistencyStrategy

ExecutionResult.model_rebuild()

CONTROLS = {
    "num_candidates": 2,
    "num_examples": 2,
    "similarity_metric": "tag_overlap",
    "min_similarity_score": 0.5,
    "example_source": "solved_problems",
    "reflection_context_chars": 10,
}
CODE = "```python\ndef solution(nums, target):\n    return [0, 1]\n```"


@pytest.fixture(params=["openai", "local", "anthropic"])
def boundary(request):
    provider = request.param
    # Anthropic 1.x uses httpx2; older supported releases use httpx.
    transport = getattr(anthropic_transport, "httpx2", httpx) if provider == "anthropic" else httpx
    bodies = []
    answers = []

    def respond(req):
        bodies.append(json.loads(req.content))
        text = answers.pop(0) if answers else CODE
        if provider == "anthropic":
            payload = {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        else:
            payload = {
                "id": "chat_test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        return transport.Response(200, json=payload)

    client = LLMClient(
        LLMConfig(
            provider=provider,
            model="test-model",
            api_key="fake-boundary-key",
            base_url="https://boundary.invalid/v1",
            temperature=0.7,
            max_tokens=100,
            retry_max_attempts=1,
            cache=CacheConfig(enabled=False),
        )
    )
    client.client.close()
    sdk = Anthropic if provider == "anthropic" else OpenAI
    client.client = sdk(
        api_key="fake-boundary-key",
        base_url="https://boundary.invalid/v1",
        max_retries=0,
        http_client=transport.Client(transport=transport.MockTransport(respond)),
    )
    yield client, bodies, answers
    client.client.close()


def config(name):
    return StrategyConfig(
        name=name,
        max_iterations=2,
        temperature=0.4,
        max_tokens=200,
        custom_params={
            **CONTROLS,
            "top_p": 0.9,
            "temperature": 0.2,
            "max_tokens": 50,
            "extra_body": {"vendor_option": True},
        },
    )


def assert_request(body):
    assert not CONTROLS.keys() & body.keys()
    assert body["top_p"] == 0.9
    assert body["temperature"] == 0.2
    assert body["max_tokens"] == 50
    assert body["vendor_option"] is True


def test_self_consistency_controls_candidate_count_at_sdk_boundary(boundary, sample_problem):
    client, bodies, _ = boundary
    sandbox = Mock()
    sandbox.execute.return_value = SandboxResult(status="success", all_passed=True)
    cfg = config("self_consistency")
    original = cfg.model_dump()
    result = SelfConsistencyStrategy(cfg, client, sandbox).execute(sample_problem)
    assert result.success
    assert len(result.iterations) == 2
    assert len(bodies) == 2
    for body in bodies:
        assert_request(body)
    assert cfg.model_dump() == original


def test_few_shot_controls_retrieval_without_leaking(boundary, sample_problem, monkeypatch):
    client, bodies, _ = boundary
    monkeypatch.setattr(FewShotLearningStrategy, "_load_example_database", lambda self: None)
    cfg = config("few_shot_learning")
    original = cfg.model_dump()
    sandbox = Mock()
    sandbox.execute.return_value = SandboxResult(status="success", all_passed=True)
    strategy = FewShotLearningStrategy(cfg, client, sandbox)
    strategy.example_db = [
        SimilarProblem(
            ExampleProblem(str(i), f"Included example {i}", "example", "easy", sample_problem.tags),
            "def solution(): pass",
            0,
            [],
        )
        for i in range(3)
    ] + [
        SimilarProblem(
            ExampleProblem("low", "Excluded low score", "example", "easy", ["unrelated"]),
            "def solution(): pass",
            0,
            [],
        )
    ]
    assert strategy.execute(sample_problem).success
    assert len(bodies) == 1
    assert_request(bodies[0])
    prompt = bodies[0]["messages"][-1]["content"]
    assert "Included example 0" in prompt and "Included example 1" in prompt
    assert "Included example 2" not in prompt and "Excluded low score" not in prompt
    assert cfg.model_dump() == original


def test_reflexion_controls_context_on_generation_and_reflection(boundary, sample_problem):
    client, bodies, answers = boundary
    answers.extend([CODE, "reflection-prefix-ABCDEFGHIJ", CODE])
    sandbox = Mock()
    sandbox.execute.side_effect = [
        SandboxResult(status="failed", all_passed=False),
        SandboxResult(status="success", all_passed=True),
    ]
    cfg = config("reflexion")
    original = cfg.model_dump()
    result = ReflexionStrategy(cfg, client, sandbox).execute(sample_problem)
    assert result.success
    assert len(bodies) == 3
    for body in bodies:
        assert_request(body)
    retry_prompt = bodies[2]["messages"][-1]["content"]
    assert "ABCDEFGHIJ" in retry_prompt
    assert "reflection-prefix" not in retry_prompt
    assert cfg.model_dump() == original


def test_cache_uses_provider_params_but_not_strategy_controls(boundary, tmp_path):
    client, bodies, _ = boundary
    client.config.cache.enabled = True
    client.cache = LLMResponseCache(cache_dir=str(tmp_path / "cache"))
    strategy = ReflexionStrategy(config("reflexion"), client, Mock())
    first = strategy.generate("same prompt")
    strategy.config.custom_params["reflection_context_chars"] = 1000
    strategy.generate("same prompt")
    assert len(bodies) == 1
    assert not CONTROLS.keys() & first.effective_params.keys()
    strategy.config.custom_params["top_p"] = 0.8
    strategy.generate("same prompt")
    assert len(bodies) == 2 and bodies[-1]["top_p"] == 0.8
    strategy.config.custom_params["extra_body"] = {"vendor_option": False}
    strategy.generate("same prompt")
    assert len(bodies) == 3 and bodies[-1]["vendor_option"] is False
