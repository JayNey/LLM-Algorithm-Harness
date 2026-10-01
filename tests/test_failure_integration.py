"""Issue #89 end-to-end persistence and report coverage."""

import json
from unittest.mock import Mock

from src.harness import AlgorithmHarness
from src.main import save_results
from src.models import (
    ExecutionResult,
    HarnessConfig,
    LLMConfig,
    SandboxConfig,
    SandboxResult,
    StrategyConfig,
)
from src.models import (
    TestCaseResult as CaseResult,
)


def test_run_persists_failure_modes_and_tag_report(tmp_path, monkeypatch):
    dataset = tmp_path / "problems.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "problem_id": key,
                    "title": key,
                    "description": "Return the required answer for this labeled problem.",
                    "difficulty": "easy",
                    "tags": tags,
                    "test_cases": [{"input": {"x": 2}, "expected_output": 3}],
                }
                for key, tags in [
                    ("syntax", ["arrays"]),
                    ("logic", ["arrays", "dp"]),
                    ("timeout", ["dp"]),
                ]
            ]
        ),
        encoding="utf-8",
    )

    def prepare(_self, _strategy_config):
        strategy = Mock()

        def execute(problem):
            status = {
                "syntax": "syntax_error",
                "logic": "wrong_answer",
                "timeout": "timeout",
            }[problem.problem_id]
            sandbox = SandboxResult(
                status="timeout" if status == "timeout" else "failed",
                all_passed=False,
                test_results=[
                    CaseResult(
                        test_case_index=0,
                        passed=False,
                        status=status,
                        expected_output=3,
                        actual_output=None if status != "wrong_answer" else 4,
                        error_message=(
                            "SyntaxError: invalid syntax" if status == "syntax_error" else None
                        ),
                    )
                ],
            )
            return ExecutionResult(
                problem_id=problem.problem_id,
                strategy="vanilla",
                generated_code="def solution(x): return x",
                status="failed",
                failure_category="wrong_answer",
                final_result=sandbox,
            )

        strategy.execute.side_effect = execute
        return strategy, Mock()

    monkeypatch.setattr(AlgorithmHarness, "_prepare_strategy_runtime", prepare)
    config = HarnessConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        llm_config=LLMConfig(provider="openai", api_key="test", model="test"),
        sandbox_config=SandboxConfig(backend="host"),
        strategies=[StrategyConfig(name="vanilla")],
        max_workers=1,
    )
    harness = AlgorithmHarness(config)
    reports = harness.run(use_task_service=True, run_id="failure-modes")
    save_results(reports, config.output_dir, harness, config)

    run_dir = tmp_path / "results" / "failure-modes"
    results = json.loads((run_dir / "vanilla_results.json").read_text())
    assert [row["failure_mode"] for row in results] == ["syntax_error", "logic_error", "timeout"]
    assert all(row["failure_mode_evidence"] for row in results)
    assert [unit.result["failure_mode"] for unit in harness.task_record.units] == [
        "syntax_error",
        "logic_error",
        "timeout",
    ]

    summary = json.loads((run_dir / "failure_mode_summary.json").read_text())
    assert summary["overall"]["total_failures"] == 3
    assert summary["overall"]["categories"]["syntax_error"]["count"] == 1
    assert summary["overall"]["by_tags"]["arrays"]["failures"] == 2
    assert summary["overall"]["by_tags"]["dp"]["failures"] == 2
    assert (run_dir / "failure_mode_distribution.png").read_bytes().startswith(b"\x89PNG")
    assert "失败模式" in (run_dir / "failure_mode_report.md").read_text()


def test_failed_task_unit_is_exported_but_excluded_from_mode_denominator(tmp_path, monkeypatch):
    dataset = tmp_path / "problems.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "problem_id": "p1",
                    "title": "P1",
                    "description": "Return the required answer for this test problem.",
                    "difficulty": "easy",
                    "tags": ["arrays"],
                    "test_cases": [{"input": {"x": 2}, "expected_output": 3}],
                }
            ]
        ),
        encoding="utf-8",
    )
    config = HarnessConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        llm_config=LLMConfig(provider="openai", api_key="test", model="test"),
        sandbox_config=SandboxConfig(backend="host"),
        strategies=[StrategyConfig(name="vanilla")],
        max_workers=1,
    )
    monkeypatch.setattr(AlgorithmHarness, "_prepare_strategy_runtime", lambda *_: (Mock(), Mock()))

    def fail(*_args):
        raise RuntimeError("Sandbox backend unavailable")

    monkeypatch.setattr(AlgorithmHarness, "_execute_problem", fail)
    harness = AlgorithmHarness(config)
    reports = harness.run(use_task_service=True, run_id="failed-unit")
    save_results(reports, config.output_dir, harness, config)
    rows = json.loads((tmp_path / "results" / "failed-unit" / "vanilla_results.json").read_text())
    assert rows[0]["evaluation_completed"] is False
    assert rows[0]["failure_mode"] is None
    summary = json.loads(
        (tmp_path / "results" / "failed-unit" / "failure_mode_summary.json").read_text()
    )
    assert summary["overall"]["total_evaluated"] == 0
    assert summary["overall"]["total_failures"] == 0
    assert harness.task_record.state == "failed"
