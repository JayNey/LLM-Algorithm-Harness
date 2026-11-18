"""Offline regressions for historical examples and target-answer isolation."""

import json
from unittest.mock import Mock

import pytest

from src.models import Problem, StrategyConfig
from src.strategies.few_shot_learning import FewShotLearningStrategy, SimilarProblem


def problem(problem_id="target", **overrides):
    values = dict(
        problem_id=problem_id,
        title="Add the values",
        description="Return the sum of all array elements.",
        difficulty="easy",
        tags=["array", "math"],
        source_platform="leetcode",
        source_problem_id="1",
        source_url="https://example.com/problems/sum/",
        public_test_cases=[{"input": {"nums": [1, 2]}, "expected_output": 3}],
    )
    return Problem(**(values | overrides))


def make_strategy():
    return FewShotLearningStrategy(
        StrategyConfig(name="few_shot_learning", custom_params={"min_similarity_score": 0}),
        Mock(),
        Mock(),
    )


def write_history(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


@pytest.mark.parametrize("identity", ["id", "source", "url", "description"])
def test_historical_target_answers_never_enter_prompt(tmp_path, monkeypatch, identity):
    monkeypatch.chdir(tmp_path)
    target = problem()
    history = problem(
        "alias",
        description="A different wording for the historical question.",
        source_problem_id="99",
        source_url="https://example.com/problems/other",
    ).model_dump()
    if identity == "id":
        history["problem_id"] = "target"
    elif identity == "source":
        history.update(source_platform=" LeetCode ", source_problem_id="1", source_version="v2")
    elif identity == "url":
        history["source_url"] = "http://EXAMPLE.com/problems/sum?lang=en#answer"
    else:
        history["description"] = "  RETURN the sum of all\narray elements.  "
    history.update(status="success", generated_code="LEAKED_TARGET_ANSWER")
    safe = problem(
        "different",
        description="Return the product of all array elements.",
        source_problem_id="2",
        source_url="https://example.com/problems/product",
    ).model_dump()
    safe.update(status="success", generated_code="SAFE_PRODUCT_ANSWER")
    write_history(tmp_path / "results" / "history_results.json", [history, safe])
    strategy = make_strategy()
    retrieved = strategy.retrieve_similar(target, k=3)
    prompt = strategy.build_few_shot_prompt(target, retrieved)
    assert [item.problem.problem_id for item in retrieved] == ["different"]
    assert "LEAKED_TARGET_ANSWER" not in prompt
    assert "SAFE_PRODUCT_ANSWER" in prompt


@pytest.mark.parametrize("threshold", [0, 0.3])
def test_prompt_builder_filters_target_even_without_retrieval(tmp_path, monkeypatch, threshold):
    monkeypatch.chdir(tmp_path)
    strategy = make_strategy()
    strategy.min_similarity_score = threshold
    target = problem()
    example = SimilarProblem(target, "LEAKED_TARGET_ANSWER", 1.0, ["array"])
    prompt = strategy.build_few_shot_prompt(target, [example])
    assert "LEAKED_TARGET_ANSWER" not in prompt
    assert prompt == strategy.build_base_prompt(target)
