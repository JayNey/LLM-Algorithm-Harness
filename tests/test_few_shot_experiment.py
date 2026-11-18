"""Fixed example conditions across real offline experiment combinations."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.experiment import ExperimentRunner
from src.models import ExperimentConfig, LLMResponse, Problem, TokenUsage


def question(identity, description):
    return Problem(
        problem_id=identity,
        title=identity,
        description=description,
        difficulty="easy",
        tags=["array"],
        source_platform="test",
        source_problem_id=identity,
        public_test_cases=[{"input": {"nums": [1, 2]}, "expected_output": 3}],
    )


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    targets = [
        question("target-a", "Add all the numbers for task A."),
        question("target-b", "Add all the numbers for task B."),
    ]
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps([p.model_dump() for p in targets]), encoding="utf-8")
    history = tmp_path / "results" / "history_results.json"
    history.parent.mkdir()
    safe = question("safe", "Compute the sum of this historical sequence.").model_dump()
    safe.update(status="success", generated_code="SAFE_HISTORICAL_ANSWER")
    alias = targets[1].model_dump() | {"problem_id": "target-b-alias"}
    alias.update(status="success", generated_code="LEAKED_EXPERIMENT_ANSWER")
    history.write_text(json.dumps([safe, alias]), encoding="utf-8")
    config = ExperimentConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "experiments"),
        models=[{"provider": "openai", "model": "offline", "api_key": "test"}],
        strategies=[{"name": "few_shot_learning"}],
        repeats=2,
        sandbox_config={"backend": "host"},
    )
    prompts = []

    def generate(prompt, **kwargs):
        prompts.append(prompt)
        assert "example_manifest" not in kwargs.get("custom_params", {})
        assert "example_set_id" not in kwargs.get("custom_params", {})
        late = question("late", "A late history answer about adding arrays.").model_dump()
        late.update(status="success", generated_code="LATE_ANSWER")
        (history.parent / "late_results.json").write_text(json.dumps([late]), encoding="utf-8")
        return LLMResponse(
            text="```python\ndef solution(nums):\n    return sum(nums)\n```",
            model="offline",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    def client_factory(config):
        client = Mock()
        client.generate.side_effect = generate
        return client

    monkeypatch.setattr("src.harness.LLMClient", client_factory)
    return config, prompts


@pytest.mark.parametrize("execution", ["serial", "parallel"])
def test_all_combinations_share_frozen_examples(experiment, execution):
    config, prompts = experiment
    config.execution = execution
    output = ExperimentRunner(config).run()
    metadata = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    frozen = metadata.get("few_shot_examples")
    assert frozen is not None, "formal experiments must record fixed example inputs"
    assert frozen["example_set_id"]
    assert frozen["excluded"][0]["problem_id"] == "target-b-alias"
    assert frozen["excluded"][0]["target_problem_id"] == "target-b"
    assert len(prompts) == 4
    assert all("SAFE_HISTORICAL_ANSWER" in prompt for prompt in prompts)
    assert all("LEAKED_EXPERIMENT_ANSWER" not in prompt for prompt in prompts)
    assert all("LATE_ANSWER" not in prompt for prompt in prompts)
    for path in output.glob("combo-*/*_results.json"):
        for row in json.loads(path.read_text(encoding="utf-8")):
            assert (
                row["metadata"]["few_shot_examples"]["example_set_id"] == frozen["example_set_id"]
            )


def paused_run(config, prompts):
    runner = ExperimentRunner(config)
    runner.checkpoint_dir = Path(config.output_dir) / "resume"
    runner.should_pause = lambda: bool(prompts)
    return runner.run()


def test_resume_keeps_original_collection_after_history_changes(experiment):
    config, prompts = experiment
    output = paused_run(config, prompts)
    saved = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    assert len(saved["combinations"]) == 1
    runner = ExperimentRunner(config)
    runner.checkpoint_dir = output
    runner.run()
    assert len(prompts) == 4
    assert all("LATE_ANSWER" not in prompt for prompt in prompts)
    after = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    assert after["few_shot_examples"] == saved["few_shot_examples"]
    assert after["combinations"][0] == saved["combinations"][0]


@pytest.mark.parametrize(
    "damage", ["missing", "changed", "legacy", "target-changed", "metadata-missing"]
)
def test_resume_rejects_unverifiable_collection_before_model_calls(experiment, damage):
    config, prompts = experiment
    output = paused_run(config, prompts)
    metadata_path = output / "experiment.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    frozen = metadata.get("few_shot_examples")
    assert frozen is not None
    manifest = output / frozen["path"]
    if damage == "missing":
        manifest.unlink()
    elif damage == "changed":
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["examples"][0]["solution_code"] = "TAMPERED"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
    elif damage == "legacy":
        del metadata["few_shot_examples"]
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    elif damage == "target-changed":
        dataset = Path(config.dataset_path)
        rows = json.loads(dataset.read_text(encoding="utf-8"))
        rows[0]["source_problem_id"] = "changed-identity"
        dataset.write_text(json.dumps(rows), encoding="utf-8")
    else:
        metadata_path.unlink()
    before = list(prompts)
    original_metadata = metadata_path.read_bytes() if metadata_path.exists() else None
    runner = ExperimentRunner(config)
    runner.checkpoint_dir = output
    with pytest.raises(ValueError, match="[Ff]rozen|[Ff]ew-[Ss]hot|[Ee]xample"):
        runner.run()
    assert prompts == before
    if original_metadata is None:
        assert not metadata_path.exists()
    else:
        assert metadata_path.read_bytes() == original_metadata
