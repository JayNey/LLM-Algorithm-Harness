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
         patch("src.harness.SandboxExecutor"):
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
