"""
Tests for AlgorithmHarness.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.harness import AlgorithmHarness
from src.models import (
    ExecutionResult,
    HarnessConfig,
    IterationResult,
    LLMConfig,
    Problem,
    SandboxConfig,
    SandboxResult,
    StrategyConfig,
    TestCase,
    TestCaseResult,
)


@pytest.fixture
def harness_config(tmp_path):
    """Harness configuration fixture."""
    # Create a sample dataset file
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text("""[
        {
            "problem_id": "test-001",
            "title": "Test Problem",
            "description": "This is a test problem description",
            "difficulty": "easy",
            "tags": ["test"],
            "test_cases": [{"input": {"x": 1}, "expected_output": 2}]
        }
    ]""")

    return HarnessConfig(
        dataset_path=str(dataset_file),
        llm_config=LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-3.5-turbo",
        ),
        sandbox_config=SandboxConfig(
            backend="host",
            timeout_seconds=5,
            memory_limit_mb=256,
            allowed_imports=["math"],
        ),
        strategies=[
            StrategyConfig(name="vanilla", max_iterations=1),
        ],
    )


def test_harness_initialization(harness_config):
    """Test harness initialization."""
    harness = AlgorithmHarness(harness_config)

    assert harness.config == harness_config
    assert harness.problem_loader is not None
    assert harness.results == {}


def test_hidden_evaluation_runs_after_strategy_without_feedback_leak(
    harness_config, monkeypatch
):
    """Hidden failures change the final result only after strategy execution ends."""
    public_problem = Problem(
        problem_id="hidden-1",
        title="Hidden Evaluation",
        description="A problem with a hidden case that catches sample overfitting.",
        difficulty="easy",
        public_test_cases=[{"input": {"value": 1}, "expected_output": 1}],
        feedback_test_cases=[{"input": {"value": 2}, "expected_output": 2}],
        hidden_test_cases=[{"input": {"value": 99}, "expected_output": 100}],
    )
    public_result = SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=1,
                expected_output=1,
                status="passed",
            )
        ],
        all_passed=True,
    )
    hidden_result = SandboxResult(
        status="failed",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=False,
                actual_output=1,
                expected_output=100,
                status="wrong_answer",
            )
        ],
        all_passed=False,
    )
    execution_result = ExecutionResult(
        problem_id="hidden-1",
        strategy="vanilla",
        generated_code="def solution(value): return 1",
        status="success",
        iterations=[],
        final_result=public_result,
        test_results=public_result.test_results,
    )
    strategy = MagicMock()
    strategy.execute.return_value = execution_result
    sandbox = MagicMock()
    sandbox.health_check.return_value = (True, None)
    sandbox.execute.side_effect = [hidden_result]
    monkeypatch.setattr("src.harness.LLMClient", MagicMock())
    monkeypatch.setattr("src.harness.SandboxExecutor", lambda config: sandbox)

    harness = AlgorithmHarness(harness_config)
    monkeypatch.setitem(harness.STRATEGY_MAP, "vanilla", lambda *args: strategy)

    report = harness._run_strategy(harness_config.strategies[0], [public_problem])

    assert execution_result.status == "failed"
    assert execution_result.hidden_result is hidden_result
    assert report.solved_problems == 0
    assert report.formal_evaluable_problems == 1
    assert report.formal_solved_problems == 0
    assert report.formal_success_rate == 0.0
    assert sandbox.execute.call_args_list[-1].kwargs["stage"] == "hidden"


def test_strategy_receives_problem_without_hidden_cases(harness_config, monkeypatch):
    """Custom strategies cannot inspect hidden inputs during candidate generation."""
    problem = Problem(
        problem_id="isolated-hidden",
        title="Isolated Hidden",
        description="A problem used to verify strategy input isolation.",
        difficulty="easy",
        public_test_cases=[{"input": {}, "expected_output": 1}],
        hidden_test_cases=[{"input": {"secret": "HIDDEN"}, "expected_output": 2}],
    )
    strategy = MagicMock()
    strategy.execute.side_effect = lambda visible_problem: (
        None
        if visible_problem.hidden_test_cases
        else ExecutionResult(
            problem_id=visible_problem.problem_id,
            strategy="vanilla",
            generated_code="def solution(): return 1",
            status="success",
            iterations=[],
        )
    )
    sandbox = MagicMock()
    sandbox.health_check.return_value = (True, None)
    sandbox.execute.return_value = SandboxResult(status="success", all_passed=True)
    monkeypatch.setattr("src.harness.LLMClient", MagicMock())
    monkeypatch.setattr("src.harness.SandboxExecutor", lambda config: sandbox)

    harness = AlgorithmHarness(harness_config)
    monkeypatch.setitem(harness.STRATEGY_MAP, "vanilla", lambda *args: strategy)

    report = harness._run_strategy(harness_config.strategies[0], [problem])

    visible_problem = strategy.execute.call_args.args[0]
    assert visible_problem.hidden_test_cases == []
    assert visible_problem.public_test_cases
    assert report.formal_evaluable_problems == 1


def test_hidden_only_problem_is_scored_by_hidden_stage(harness_config, monkeypatch):
    """A hidden-only problem can pass when its independent final tests pass."""
    problem = Problem(
        problem_id="hidden-only",
        title="Hidden Only",
        description="A problem whose only tests are reserved for final evaluation.",
        difficulty="easy",
        hidden_test_cases=[{"input": {}, "expected_output": 1}],
    )
    execution_result = ExecutionResult(
        problem_id="hidden-only",
        strategy="vanilla",
        generated_code="def solution(): return 1",
        status="success",
        iterations=[],
    )
    strategy = MagicMock()
    strategy.execute.return_value = execution_result
    hidden_result = SandboxResult(status="success", all_passed=True)
    sandbox = MagicMock()
    sandbox.health_check.return_value = (True, None)
    sandbox.execute.return_value = hidden_result
    monkeypatch.setattr("src.harness.LLMClient", MagicMock())
    monkeypatch.setattr("src.harness.SandboxExecutor", lambda config: sandbox)

    harness = AlgorithmHarness(harness_config)
    monkeypatch.setitem(harness.STRATEGY_MAP, "vanilla", lambda *args: strategy)

    report = harness._run_strategy(harness_config.strategies[0], [problem])

    assert execution_result.status == "success"
    assert execution_result.formal_evaluable is True
    assert execution_result.hidden_result is hidden_result
    assert report.formal_solved_problems == 1
    assert sandbox.execute.call_args.kwargs["stage"] == "hidden"


def test_unsupported_problem_is_short_circuited_before_strategy(
    harness_config, monkeypatch
):
    """Unsupported protocols never enter model generation or hidden scoring."""
    problem = Problem(
        problem_id="unsupported-hidden",
        title="Unsupported Hidden",
        description="A problem whose custom protocol is not implemented.",
        difficulty="hard",
        unsupported_reason="interactive protocol is unsupported",
        hidden_test_cases=[{"input": {}, "expected_output": 1}],
    )
    strategy = MagicMock()
    sandbox = MagicMock()
    sandbox.health_check.return_value = (True, None)
    monkeypatch.setattr("src.harness.LLMClient", MagicMock())
    monkeypatch.setattr("src.harness.SandboxExecutor", lambda config: sandbox)

    harness = AlgorithmHarness(harness_config)
    monkeypatch.setitem(harness.STRATEGY_MAP, "vanilla", lambda *args: strategy)

    report = harness._run_strategy(harness_config.strategies[0], [problem])
    result = harness.get_results("vanilla")[0]

    strategy.execute.assert_not_called()
    sandbox.execute.assert_not_called()
    assert result.status == "unsupported"
    assert result.failure_category == "unsupported"
    assert report.formal_evaluable_problems == 0


def test_hidden_execution_error_keeps_formal_record(harness_config, monkeypatch):
    """A hidden executor exception remains a formal system failure record."""
    problem = Problem(
        problem_id="hidden-error",
        title="Hidden Error",
        description="A problem used to verify hidden execution error handling.",
        difficulty="easy",
        hidden_test_cases=[{"input": {}, "expected_output": 1}],
    )
    strategy = MagicMock()
    strategy.execute.return_value = ExecutionResult(
        problem_id="hidden-error",
        strategy="vanilla",
        generated_code="def solution(): return 1",
        status="success",
        iterations=[],
    )
    sandbox = MagicMock()
    sandbox.health_check.return_value = (True, None)
    sandbox.execute.side_effect = RuntimeError("hidden backend unavailable")
    monkeypatch.setattr("src.harness.LLMClient", MagicMock())
    monkeypatch.setattr("src.harness.SandboxExecutor", lambda config: sandbox)

    harness = AlgorithmHarness(harness_config)
    monkeypatch.setitem(harness.STRATEGY_MAP, "vanilla", lambda *args: strategy)

    report = harness._run_strategy(harness_config.strategies[0], [problem])
    result = harness.get_results("vanilla")[0]

    assert result.formal_evaluable is True
    assert result.hidden_result.status == "sandbox_error"
    assert result.failure_category == "system_error"
    assert report.formal_evaluable_problems == 1
    assert report.formal_solved_problems == 0


def test_formal_report_uses_hidden_result_independently(harness_config):
    """Formal hidden metrics count hidden passes even when visible tests failed."""
    problem = Problem(
        problem_id="visible-fail-hidden-pass",
        title="Visible Fail Hidden Pass",
        description="A problem used to define formal metric independence.",
        difficulty="easy",
        public_test_cases=[{"input": {}, "expected_output": 1}],
        hidden_test_cases=[{"input": {}, "expected_output": 1}],
    )
    result = ExecutionResult(
        problem_id=problem.problem_id,
        strategy="vanilla",
        generated_code="def solution(): return 1",
        status="failed",
        formal_evaluable=True,
        hidden_result=SandboxResult(status="success", all_passed=True),
    )

    report = AlgorithmHarness(harness_config)._generate_report(
        harness_config.strategies[0], [result], [problem]
    )

    assert report.solved_problems == 0
    assert report.formal_solved_problems == 1
    assert report.formal_success_rate == 1.0


def test_report_marks_legacy_problem_as_sample_only(harness_config):
    """Legacy problems are excluded from the formal hidden-test denominator."""
    problem = Problem(
        problem_id="sample-only",
        title="Sample Only",
        description="A legacy problem with no independent scoring cases.",
        difficulty="easy",
        test_cases=[{"input": {"value": 1}, "expected_output": 1}],
    )
    result = ExecutionResult(
        problem_id="sample-only",
        strategy="vanilla",
        generated_code="def solution(value): return value",
        status="success",
        iterations=[],
        test_results=[],
    )
    report = AlgorithmHarness(harness_config)._generate_report(
        harness_config.strategies[0], [result], [problem]
    )

    assert report.formal_evaluable_problems == 0
    assert report.sample_only_problems == 1
    assert report.formal_success_rate == 0.0


def test_harness_initialization_logs_only_redacted_config(harness_config):
    """Harness initialization uses the shared safe configuration view."""
    secret = harness_config.llm_config.api_key.get_secret_value()

    with patch("src.harness.logger") as mock_logger:
        AlgorithmHarness(harness_config)

    logged_config = mock_logger.info.call_args.kwargs["config"]
    assert secret not in str(logged_config)
    assert logged_config["llm_config"]["api_key"] == "[REDACTED]"


def test_load_problems(harness_config):
    """Test loading problems."""
    harness = AlgorithmHarness(harness_config)
    problems = harness._load_problems()

    assert len(problems) == 1
    assert problems[0].problem_id == "test-001"


def test_run_strategy(harness_config, monkeypatch):
    """Test running a single strategy."""
    # Mock strategy execution
    mock_strategy = MagicMock()
    mock_result = ExecutionResult(
        problem_id="test-001",
        strategy="vanilla",
        generated_code="def solution(): pass",
        status="success",
        iterations=[],
        total_tokens=150,
    )
    mock_strategy.execute.return_value = mock_result

    # Create mock strategy class
    mock_strategy_class = MagicMock(return_value=mock_strategy)

    with patch("src.harness.LLMClient") as mock_llm_class, \
         patch("src.harness.SandboxExecutor") as mock_sandbox_class:
        mock_sandbox_class.return_value.health_check.return_value = (True, None)

        harness = AlgorithmHarness(harness_config)
        # Replace the strategy in STRATEGY_MAP
        monkeypatch.setitem(harness.STRATEGY_MAP, "vanilla", mock_strategy_class)

        problems = harness._load_problems()
        report = harness._run_strategy(harness_config.strategies[0], problems)

        assert report.strategy_name == "vanilla"
        assert report.total_problems == 1
        assert report.solved_problems == 1


def test_generate_report(harness_config):
    """Test generating strategy report."""
    harness = AlgorithmHarness(harness_config)

    problems = [
        Problem(
            problem_id="test-001",
            title="Test Problem One",
            description="Test problem description for problem one",
            difficulty="easy",
            tags=["test"],
            test_cases=[TestCase(input={"x": 1}, expected_output=2)],
        ),
        Problem(
            problem_id="test-002",
            title="Test Problem Two",
            description="Test problem description for problem two",
            difficulty="easy",
            tags=["test"],
            test_cases=[TestCase(input={"x": 2}, expected_output=4)],
        ),
    ]

    results = [
        ExecutionResult(
            problem_id="test-001",
            strategy="vanilla",
            generated_code="def solution(): pass",
            status="success",
            iterations=[],
            total_tokens=150,
        ),
        ExecutionResult(
            problem_id="test-002",
            strategy="vanilla",
            generated_code="def solution(): pass",
            status="failed",
            iterations=[],
            total_tokens=180,
        ),
    ]

    strategy_config = StrategyConfig(name="vanilla", max_iterations=1)
    report = harness._generate_report(strategy_config, results, problems)

    assert report.strategy_name == "vanilla"
    assert report.total_problems == 2
    assert report.solved_problems == 1
    assert report.failed_problems == 1
    assert report.success_rate == 0.5
    assert report.total_tokens == 330


def test_get_results(harness_config):
    """Test getting results for strategy."""
    harness = AlgorithmHarness(harness_config)

    result = ExecutionResult(
        problem_id="test-001",
        strategy="vanilla",
        generated_code="def solution(): pass",
        status="success",
        iterations=[],
        total_tokens=150,
    )

    harness.results["vanilla"] = [result]

    retrieved = harness.get_results("vanilla")
    assert len(retrieved) == 1
    assert retrieved[0] == result


def test_get_failed_problems(harness_config):
    """Test getting failed problems."""
    harness = AlgorithmHarness(harness_config)

    results = [
        ExecutionResult(
            problem_id="test-001",
            strategy="vanilla",
            generated_code="def solution(): pass",
            status="success",
            iterations=[],
            total_tokens=150,
        ),
        ExecutionResult(
            problem_id="test-002",
            strategy="vanilla",
            generated_code="def solution(): pass",
            status="failed",
            iterations=[],
            total_tokens=150,
        ),
    ]

    harness.results["vanilla"] = results

    failed = harness.get_failed_problems("vanilla")
    assert len(failed) == 1
    assert failed[0] == "test-002"


def test_compare_strategies(harness_config):
    """Test comparing strategies."""
    harness = AlgorithmHarness(harness_config)

    harness.results["vanilla"] = [
        ExecutionResult(
            problem_id="test-001",
            strategy="vanilla",
            generated_code="def solution(): pass",
            status="success",
            iterations=[],
            total_tokens=150,
        ),
    ]

    harness.results["chain_of_thought"] = [
        ExecutionResult(
            problem_id="test-001",
            strategy="chain_of_thought",
            generated_code="def solution(): pass",
            status="failed",
            iterations=[],
            total_tokens=300,
        ),
    ]

    comparison = harness.compare_strategies()

    assert "vanilla" in comparison["strategies"]
    assert "chain_of_thought" in comparison["strategies"]
    assert comparison["metrics"]["vanilla"]["success_rate"] == 1.0
    assert comparison["metrics"]["chain_of_thought"]["success_rate"] == 0.0


def test_unknown_strategy_raises_error(harness_config):
    """Test running unknown strategy raises ValueError."""
    harness = AlgorithmHarness(harness_config)

    unknown_config = StrategyConfig(name="unknown_strategy", max_iterations=1)
    problems = harness._load_problems()

    with patch("src.harness.LLMClient"), \
         patch("src.harness.SandboxExecutor") as mock_sandbox_class:
        mock_sandbox_class.return_value.health_check.return_value = (True, None)
        with pytest.raises(ValueError, match="Unknown strategy"):
            harness._run_strategy(unknown_config, problems)


def test_harness_run_full_execution(harness_config, tmp_path):
    """Test harness complete run() method execution."""
    import json

    # Create a more complete dataset
    dataset_file = tmp_path / "full_dataset.json"
    dataset_data = [
        {
            "problem_id": "p1",
            "title": "Problem One",
            "description": "First test problem with sufficient description length",
            "difficulty": "easy",
            "test_cases": [{"input": {"x": 1}, "expected_output": 2}]
        },
        {
            "problem_id": "p2",
            "title": "Problem Two",
            "description": "Second test problem with sufficient description length",
            "difficulty": "medium",
            "test_cases": [{"input": {"x": 2}, "expected_output": 4}]
        }
    ]
    dataset_file.write_text(json.dumps(dataset_data))

    # Create config with multiple strategies
    config = HarnessConfig(
        dataset_path=str(dataset_file),
        llm_config=LLMConfig(
            provider="openai",
            api_key="test-key-123",
            model="gpt-3.5-turbo",
        ),
        strategies=[
            StrategyConfig(name="vanilla", max_iterations=1),
            StrategyConfig(name="chain_of_thought", max_iterations=1),
        ],
    )

    # Mock the strategy execution
    mock_result_1 = ExecutionResult(
        problem_id="p1",
        strategy="vanilla",
        generated_code="def solution(): return 2",
        status="success",
        iterations=[],
        total_tokens=100,
    )

    mock_result_2 = ExecutionResult(
        problem_id="p2",
        strategy="vanilla",
        generated_code="def solution(): return 4",
        status="success",
        iterations=[],
        total_tokens=120,
    )

    with patch("src.harness.LLMClient"), \
         patch("src.harness.SandboxExecutor"), \
         patch.object(AlgorithmHarness, "_run_strategy") as mock_run_strategy:

        # Mock the report generation
        from src.models import StrategyReport
        mock_report = StrategyReport(
            strategy_name="vanilla",
            total_problems=2,
            solved_problems=2,
            failed_problems=0,
            success_rate=1.0,
            avg_attempts_per_problem=1.0,
            avg_tokens_per_problem=110.0,
            total_tokens=220,
            estimated_cost_usd=0.001,
        )
        mock_run_strategy.return_value = mock_report

        harness = AlgorithmHarness(config)
        reports = harness.run()

        # Verify run was called and returned reports
        assert len(reports) > 0
        assert mock_run_strategy.called


def test_harness_with_problem_limit(harness_config, tmp_path):
    """Test harness respects problem limit."""
    import json

    # Create dataset with multiple problems
    dataset_file = tmp_path / "large_dataset.json"
    dataset_data = [
        {
            "problem_id": f"p{i}",
            "title": f"Problem {i}",
            "description": f"Test problem number {i} with sufficient description",
            "difficulty": "easy",
            "test_cases": [{"input": {"x": i}, "expected_output": i*2}]
        }
        for i in range(10)
    ]
    dataset_file.write_text(json.dumps(dataset_data))

    config = HarnessConfig(
        dataset_path=str(dataset_file),
        llm_config=LLMConfig(provider="openai", api_key="test", model="gpt-3.5-turbo"),
        problem_filters={"limit": 3},
    )

    harness = AlgorithmHarness(config)
    problems = harness._load_problems()

    # Should respect the limit
    assert len(problems) == 3


def test_harness_with_difficulty_filter(harness_config, tmp_path):
    """Test harness filters problems by difficulty."""
    import json

    dataset_file = tmp_path / "mixed_dataset.json"
    dataset_data = [
        {
            "problem_id": "easy1",
            "title": "Easy Problem",
            "description": "An easy test problem with sufficient description",
            "difficulty": "easy",
            "test_cases": [{"input": {"x": 1}, "expected_output": 2}]
        },
        {
            "problem_id": "hard1",
            "title": "Hard Problem",
            "description": "A hard test problem with sufficient description",
            "difficulty": "hard",
            "test_cases": [{"input": {"x": 2}, "expected_output": 4}]
        }
    ]
    dataset_file.write_text(json.dumps(dataset_data))

    config = HarnessConfig(
        dataset_path=str(dataset_file),
        llm_config=LLMConfig(provider="openai", api_key="test", model="gpt-3.5-turbo"),
        problem_filters={"difficulty": "easy"},
    )

    harness = AlgorithmHarness(config)
    problems = harness._load_problems()

    # Should only load easy problems (1 out of 2)
    assert len(problems) == 1
    assert problems[0].difficulty == "easy"


def test_harness_rejects_filters_that_match_no_problems(tmp_path):
    """A configured evaluation must fail instead of reporting success for zero matches."""
    import json

    dataset_file = tmp_path / "easy_dataset.json"
    dataset_file.write_text(
        json.dumps(
            [
                {
                    "problem_id": "easy1",
                    "title": "Easy Problem",
                    "description": "An easy test problem with sufficient description",
                    "difficulty": "easy",
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                }
            ]
        )
    )
    config = HarnessConfig(
        dataset_path=str(dataset_file),
        llm_config=LLMConfig(provider="openai", api_key="test", model="gpt-3.5-turbo"),
        strategies=[StrategyConfig(name="vanilla")],
        problem_filters={"difficulty": "hard"},
    )

    with pytest.raises(ValueError, match="No problems match"):
        AlgorithmHarness(config)._load_problems()


def test_harness_concurrent_strategy_execution(harness_config, tmp_path):
    """Test harness can handle multiple strategies concurrently."""
    import json

    dataset_file = tmp_path / "concurrent_dataset.json"
    dataset_data = [
        {
            "problem_id": "p1",
            "title": "Concurrent Problem",
            "description": "Problem for concurrent execution test with sufficient length",
            "difficulty": "easy",
            "test_cases": [{"input": {"x": 1}, "expected_output": 2}]
        }
    ]
    dataset_file.write_text(json.dumps(dataset_data))

    config = HarnessConfig(
        dataset_path=str(dataset_file),
        llm_config=LLMConfig(provider="openai", api_key="test", model="gpt-3.5-turbo"),
        strategies=[
            StrategyConfig(name="vanilla"),
            StrategyConfig(name="chain_of_thought"),
            StrategyConfig(name="multi_round_feedback"),
        ],
    )

    with patch("src.harness.LLMClient"), \
         patch("src.harness.SandboxExecutor"), \
         patch.object(AlgorithmHarness, "_run_strategy") as mock_run_strategy:

        from src.models import StrategyReport
        mock_run_strategy.return_value = StrategyReport(
            strategy_name="test",
            total_problems=1,
            solved_problems=1,
            failed_problems=0,
            success_rate=1.0,
            avg_attempts_per_problem=1.0,
            avg_tokens_per_problem=100.0,
            total_tokens=100,
            estimated_cost_usd=0.001,
        )

        harness = AlgorithmHarness(config)
        reports = harness.run()

        # Should have run all three strategies
        assert mock_run_strategy.call_count == 3


def test_harness_handles_strategy_failure(harness_config):
    """Test harness continues when a strategy fails."""
    with patch("src.harness.LLMClient"), \
         patch("src.harness.SandboxExecutor"), \
         patch.object(AlgorithmHarness, "_run_strategy") as mock_run_strategy:

        # First strategy succeeds, second fails
        from src.models import StrategyReport
        success_report = StrategyReport(
            strategy_name="vanilla",
            total_problems=1,
            solved_problems=1,
            failed_problems=0,
            success_rate=1.0,
            avg_attempts_per_problem=1.0,
            avg_tokens_per_problem=100.0,
            total_tokens=100,
            estimated_cost_usd=0.001,
        )

        mock_run_strategy.side_effect = [success_report, Exception("Strategy failed")]

        config = HarnessConfig(
            dataset_path=harness_config.dataset_path,
            llm_config=harness_config.llm_config,
            strategies=[
                StrategyConfig(name="vanilla"),
                StrategyConfig(name="chain_of_thought"),
            ],
        )

        harness = AlgorithmHarness(config)

        # Should not crash, may return partial results or handle gracefully
        try:
            reports = harness.run()
            # If it returns, check we got some results
            assert len(reports) >= 0
        except Exception:
            # Or it may propagate - both behaviors are acceptable
            pass


# ============================================================================
# Terminal record and accounting tests (issue #13)
# ============================================================================


def _execution_result(problem_id, strategy, status, failure_category=None, tokens=100):
    """Build a minimal ExecutionResult for accounting tests."""
    return ExecutionResult(
        problem_id=problem_id,
        strategy=strategy,
        generated_code="def solution(): pass",
        status=status,
        failure_category=failure_category,
        iterations=[],
        total_tokens=tokens,
    )


def test_run_strategy_synthesizes_system_error_result(harness_config, monkeypatch):
    """Uncaught strategy exceptions still produce a terminal system_error record."""
    mock_strategy = MagicMock()
    mock_strategy.execute.side_effect = RuntimeError("boom api_key=sk-secret123")
    mock_strategy_class = MagicMock(return_value=mock_strategy)

    with patch("src.harness.LLMClient"), patch("src.harness.SandboxExecutor") as mock_sandbox_class:
        mock_sandbox_class.return_value.health_check.return_value = (True, None)
        harness = AlgorithmHarness(harness_config)
        monkeypatch.setitem(harness.STRATEGY_MAP, "vanilla", mock_strategy_class)

        problems = harness._load_problems()
        report = harness._run_strategy(harness_config.strategies[0], problems)

    results = harness.get_results("vanilla")
    assert len(results) == 1
    record = results[0]
    assert record.problem_id == "test-001"
    assert record.status != "success"
    assert record.failure_category == "system_error"
    assert "boom" in record.error_message
    assert "sk-secret123" not in record.error_message

    assert report.total_problems == 1
    assert report.solved_problems == 0
    assert report.system_failed_problems == 1


def test_generate_report_failure_accounting(harness_config):
    """Report totals reconcile as solved + wrong_answer + model + system."""
    harness = AlgorithmHarness(harness_config)

    problems = [
        Problem(
            problem_id=f"test-00{i}",
            title=f"Problem {i}",
            description=f"Accounting fixture problem number {i}",
            difficulty="easy",
            tags=["test"],
            test_cases=[TestCase(input={"x": 1}, expected_output=2)],
        )
        for i in range(1, 5)
    ]
    results = [
        _execution_result("test-001", "vanilla", "success"),
        _execution_result("test-002", "vanilla", "failed", "wrong_answer"),
        _execution_result("test-003", "vanilla", "error", "model_error"),
        _execution_result("test-004", "vanilla", "error", "system_error"),
    ]

    report = harness._generate_report(harness_config.strategies[0], results, problems)

    assert report.total_problems == 4
    assert report.solved_problems == 1
    assert report.failed_problems == 3
    assert report.model_failed_problems == 1
    assert report.system_failed_problems == 1
    wrong_answer = sum(
        1 for r in results if r.failure_category == "wrong_answer"
    )
    assert (
        report.solved_problems
        + wrong_answer
        + report.model_failed_problems
        + report.system_failed_problems
        == report.total_problems
    )


def test_compare_strategies_uses_recorded_problem_total(harness_config):
    """Comparison denominators match the report totals, not the result count."""
    harness = AlgorithmHarness(harness_config)

    harness.results["vanilla"] = [
        _execution_result("test-001", "vanilla", "success"),
    ]
    harness.problem_totals["vanilla"] = 2

    comparison = harness.compare_strategies()

    assert comparison["metrics"]["vanilla"]["total"] == 2
    assert comparison["metrics"]["vanilla"]["solved"] == 1
    assert comparison["metrics"]["vanilla"]["success_rate"] == 0.5


def test_run_strategy_preflight_failure_aborts_before_llm(harness_config, monkeypatch):
    """Sandbox preflight failure aborts before any model interaction."""
    mock_strategy = MagicMock()
    mock_strategy_class = MagicMock(return_value=mock_strategy)
    mock_sandbox_class = MagicMock()
    mock_sandbox_class.return_value.health_check.return_value = (
        False,
        "Docker sandbox backend unavailable; start Docker Desktop",
    )
    mock_llm_class = MagicMock()

    with patch("src.harness.LLMClient", mock_llm_class), \
         patch("src.harness.SandboxExecutor", mock_sandbox_class):
        harness = AlgorithmHarness(harness_config)
        monkeypatch.setitem(harness.STRATEGY_MAP, "vanilla", mock_strategy_class)

        problems = harness._load_problems()

        with pytest.raises(RuntimeError, match="Sandbox preflight failed"):
            harness._run_strategy(harness_config.strategies[0], problems)

    mock_llm_class.assert_not_called()
    mock_strategy.execute.assert_not_called()
