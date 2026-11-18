"""Offline regressions for historical examples and target-answer isolation."""

import json
from unittest.mock import Mock

import pytest

from src.models import (
    ExecutionResult,
    HarnessConfig,
    LLMConfig,
    LLMResponse,
    Problem,
    SandboxConfig,
    StrategyConfig,
    TokenUsage,
)
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


def test_real_result_write_load_retrieve_and_prompt(tmp_path, monkeypatch):
    from src.harness import AlgorithmHarness
    from src.main import save_results

    monkeypatch.chdir(tmp_path)
    historical = problem(
        "historical",
        feedback_test_cases=[{"input": {"nums": [3]}, "expected_output": 3}],
        hidden_test_cases=[{"input": {"nums": [4, 5]}, "expected_output": 9}],
    )
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps([historical.model_dump()]), encoding="utf-8")
    client = Mock()
    client.generate.return_value = LLMResponse(
        text="```python\ndef solution(nums):\n    return sum(nums)\n```",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model="offline",
    )
    monkeypatch.setattr("src.harness.LLMClient", lambda config: client)
    config = HarnessConfig(
        llm_config=LLMConfig(provider="openai", model="offline", api_key="test"),
        sandbox_config=SandboxConfig(backend="host"),
        dataset_path=str(dataset),
        strategies=[StrategyConfig(name="vanilla")],
        output_dir=str(tmp_path / "results"),
    )
    harness = AlgorithmHarness(config)
    reports = harness.run()
    output = save_results(reports, config.output_dir, harness, config)
    stored = json.loads((output / "vanilla_results.json").read_text(encoding="utf-8"))[0]
    snapshot = stored.get("problem_snapshot")
    assert snapshot is not None, "standard strategy output must carry real problem metadata"
    assert snapshot["title"] == "Add the values"
    assert snapshot["tags"] == ["array", "math"]
    assert snapshot["source_problem_id"] == "1"
    assert not {"public_test_cases", "feedback_test_cases", "hidden_test_cases"} & snapshot.keys()
    assert ExecutionResult.model_validate(stored).problem_snapshot is not None
    old = {key: value for key, value in stored.items() if key != "problem_snapshot"}
    assert ExecutionResult.model_validate(old).problem_id == "historical"

    strategy = make_strategy()
    target = problem(
        "new",
        description="Compute the product of the array elements.",
        source_problem_id="2",
        source_url="https://example.com/problems/product",
    )
    retrieved = strategy.retrieve_similar(target, 2)
    assert [entry.problem.problem_id for entry in retrieved] == ["historical"]
    prompt = strategy.build_few_shot_prompt(target, retrieved)
    assert "Return the sum of all array elements." in prompt
    assert "return sum(nums)" in prompt
    from src.sandbox_executor import SandboxExecutor

    strategy.llm_client = client
    strategy.sandbox = SandboxExecutor(SandboxConfig(backend="host"))
    result = strategy.execute(target)
    audit = result.metadata.get("few_shot_examples", {})
    assert audit.get("example_set_id")
    assert audit["selected"][0]["problem_id"] == "historical"
    assert audit["selected"][0]["sources"][0]["file"].endswith("vanilla_results.json")


def legacy_row(**overrides):
    row = problem("historical").model_dump()
    row.update(status="success", generated_code="def solution(nums): return sum(nums)")
    return row | overrides


def test_loader_isolates_invalid_rows_and_warns_for_missing_metadata(tmp_path, monkeypatch):
    from structlog.testing import capture_logs

    monkeypatch.chdir(tmp_path)
    rows = [
        None,
        {"problem_id": "old", "status": "success", "generated_code": "OLD_ANSWER"},
        legacy_row(problem_id="incomplete", evaluation_completed=False),
        legacy_row(problem_id="hidden-failed", hidden_result={"all_passed": False}),
        legacy_row(problem_id="failed-test", test_results=[{"passed": False}]),
        legacy_row(problem_id="future", problem_snapshot={"schema_version": 999}),
        legacy_row(problem_id="bad-tags", tags="array"),
        legacy_row(problem_id="valid"),
    ]
    write_history(tmp_path / "results" / "history_results.json", rows)
    (tmp_path / "results" / "broken_results.json").write_text("{broken", encoding="utf-8")
    with capture_logs() as logs:
        strategy = make_strategy()
    assert [entry.problem.problem_id for entry in strategy.example_db] == ["valid"]
    assert any(log["event"] == "historical_example_skipped" for log in logs)
    assert any(log["event"] == "legacy_example_metadata" for log in logs)


def test_collection_identity_tracks_content_and_not_scan_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "results" / "history_results.json"
    rows = [
        legacy_row(problem_id="a"),
        legacy_row(problem_id="b", description="Another array task."),
    ]
    write_history(path, rows)
    first = make_strategy().example_set_id
    write_history(path, list(reversed(rows)))
    assert make_strategy().example_set_id == first
    rows[0]["generated_code"] = "def solution(nums): return 42"
    write_history(path, rows)
    assert make_strategy().example_set_id != first


def test_legacy_nested_metadata_and_missing_source_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    historical = legacy_row(source_platform="legacy", source_problem_id=None, source_url=None)
    row = {
        "problem_id": "historical",
        "status": "success",
        "generated_code": historical.pop("generated_code"),
        "problem_metadata": historical,
    }
    write_history(tmp_path / "results" / "history_results.json", [row])
    strategy = make_strategy()
    duplicate = problem("renamed", description="RETURN the sum of all array elements.")
    assert strategy.retrieve_similar(duplicate, 3) == []
    different = problem("other", description="Return the product of the array elements.")
    assert len(strategy.retrieve_similar(different, 3)) == 1
    audit = strategy.build_few_shot_prompt(duplicate, strategy.example_db)
    assert "return sum(nums)" not in audit


@pytest.mark.parametrize(
    "field,value",
    [
        ("tags", ["different"]),
        ("title", "Changed title"),
        ("description", "A different historical problem statement."),
        ("source_problem_id", "new-source-id"),
    ],
)
def test_collection_identity_includes_question_inputs(tmp_path, monkeypatch, field, value):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "results" / "history_results.json"
    row = legacy_row()
    write_history(path, [row])
    before = make_strategy().example_set_id
    row[field] = value
    write_history(path, [row])
    assert make_strategy().example_set_id != before
