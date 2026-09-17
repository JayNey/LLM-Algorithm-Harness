"""
Tests for core data models.
"""

import pickle

import pytest
import yaml
from pydantic import ValidationError

from src.models import (
    ComparisonResult,
    ExecutionResult,
    ExecutionSummary,
    HarnessConfig,
    LLMConfig,
    LLMResponse,
    Problem,
    ProviderResponse,
    SandboxConfig,
    SandboxResult,
    StrategyConfig,
    StrategyMetrics,
    StrategyReport,
    TestCase,
    TestCaseResult,
    TokenUsage,
)


# ============================================================================
# TestCase Tests
# ============================================================================


def test_create_valid_test_case():
    """Test creating a valid TestCase."""
    tc = TestCase(input={"nums": [2, 7], "target": 9}, expected_output=[0, 1])

    assert tc.input == {"nums": [2, 7], "target": 9}
    assert tc.expected_output == [0, 1]


def test_test_case_json_serialization():
    """Test TestCase JSON serialization/deserialization."""
    tc = TestCase(input={"x": 1}, expected_output=2)

    json_str = tc.model_dump_json()
    assert isinstance(json_str, str)
    assert "input" in json_str

    tc2 = TestCase.model_validate_json(json_str)
    assert tc2.input == tc.input
    assert tc2.expected_output == tc.expected_output


# ============================================================================
# Problem Tests
# ============================================================================


def test_create_valid_problem():
    """Test creating a valid Problem object."""
    problem = Problem(
        problem_id="test-001",
        title="Two Sum",
        description="Given an array of integers...",
        difficulty="easy",
        tags=["array", "hash-table"],
        test_cases=[TestCase(input={"nums": [2, 7], "target": 9}, expected_output=[0, 1])],
        constraints="2 <= nums.length <= 10^4",
    )

    assert problem.problem_id == "test-001"
    assert problem.difficulty == "easy"
    assert len(problem.test_cases) == 1
    assert problem.validate_completeness() is True


def test_problem_json_serialization():
    """Test Problem JSON serialization and deserialization."""
    problem = Problem(
        problem_id="test-001",
        title="Test",
        description="Description here",
        difficulty="medium",
        tags=["test"],
        test_cases=[TestCase(input={"x": 1}, expected_output=2)],
    )

    json_str = problem.model_dump_json()
    assert isinstance(json_str, str)
    assert "problem_id" in json_str

    problem2 = Problem.model_validate_json(json_str)
    assert problem2.problem_id == problem.problem_id
    assert problem2.test_cases[0].input == problem.test_cases[0].input


def test_problem_with_empty_test_cases():
    """Test that empty test_cases list raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Problem(
            problem_id="test-001",
            title="Test",
            description="Description",
            difficulty="easy",
            tags=[],
            test_cases=[],
        )

    assert "test_cases" in str(exc_info.value)


def test_problem_with_invalid_difficulty():
    """Test that invalid difficulty raises ValidationError."""
    with pytest.raises(ValidationError):
        Problem(
            problem_id="test-001",
            title="Test",
            description="Description",
            difficulty="超难",  # Invalid value
            tags=[],
            test_cases=[TestCase(input={}, expected_output=None)],
        )


def test_problem_missing_required_field():
    """Test that missing required field raises ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Problem(
            problem_id="test-001",
            # Missing title
            description="Description",
            difficulty="easy",
            tags=[],
            test_cases=[TestCase(input={}, expected_output=None)],
        )

    assert "title" in str(exc_info.value)


# ============================================================================
# ExecutionResult Tests
# ============================================================================


def test_create_execution_result():
    """Test creating an ExecutionResult object."""
    result = ExecutionResult(
        problem_id="test-001",
        strategy="vanilla",
        generated_code="def solution(): pass",
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.01,
                status="passed",
            )
        ],
        error_message=None,
        iterations=[],
        total_tokens=350,
        execution_time_seconds=1.2,
        timestamp="2026-09-14T10:00:00",
    )

    assert result.success is True
    assert result.total_tokens == 350
    assert len(result.iterations) == 0


def test_execution_result_with_negative_tokens():
    """Test that negative tokens raises ValidationError."""
    with pytest.raises(ValidationError):
        ExecutionResult(
            problem_id="test-001",
            strategy="vanilla",
            generated_code="code",
            status="success",
            test_results=[],
            error_message=None,
            iterations=[],
            total_tokens=-100,  # Invalid
            execution_time_seconds=1.0,
            timestamp="2026-09-14T10:00:00",
        )


def test_execution_result_is_successful_false():
    """Test is_successful returns False when tests fail."""
    result = ExecutionResult(
        problem_id="test-001",
        strategy="vanilla",
        generated_code="code",
        status="failed",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=False,
                actual_output=[0, 0],
                expected_output=[0, 1],
                status="wrong_answer",
            )
        ],
        error_message="Test failed",
        iterations=[],
        total_tokens=350,
        execution_time_seconds=1.2,
        timestamp="2026-09-14T10:00:00",
    )

    assert result.success is False


# ============================================================================
# TokenUsage Tests
# ============================================================================


def test_token_usage_cost_estimate():
    """Test TokenUsage cost estimation."""
    usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)

    cost = usage.cost_estimate_usd
    assert cost > 0
    assert isinstance(cost, float)
    # Rough check: 1000 * 0.0005 / 1000 + 500 * 0.0015 / 1000 = 0.0005 + 0.00075 = 0.00125
    assert abs(cost - 0.00125) < 0.0001


# ============================================================================
# Configuration Tests
# ============================================================================


def test_create_llm_config():
    """Test creating LLMConfig."""
    config = LLMConfig(
        provider="openai",
        api_key="sk-test",
        model="gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=2000,
        timeout=30,
    )

    assert config.provider == "openai"
    assert config.model == "gpt-3.5-turbo"
    assert config.temperature == 0.7


def test_llm_config_invalid_provider():
    """Test that invalid provider raises ValidationError."""
    with pytest.raises(ValidationError):
        LLMConfig(
            provider="invalid_provider",  # Not in Literal
            api_key="test",
            model="model",
        )


def test_create_sandbox_config():
    """Test creating SandboxConfig with defaults."""
    config = SandboxConfig()

    assert config.timeout_seconds == 5
    assert config.memory_limit_mb == 256
    assert "math" in config.allowed_imports


def test_sandbox_config_custom_values():
    """Test SandboxConfig with custom values."""
    config = SandboxConfig(
        timeout_seconds=10, memory_limit_mb=512, allowed_imports=["math", "numpy"]
    )

    assert config.timeout_seconds == 10
    assert config.memory_limit_mb == 512
    assert "numpy" in config.allowed_imports


def test_strategy_config():
    """Test creating StrategyConfig."""
    config = StrategyConfig(
        name="vanilla", max_iterations=3, temperature=0.8, max_tokens=1500
    )

    assert config.name == "vanilla"
    assert config.max_iterations == 3
    assert config.temperature == 0.8


def test_harness_config():
    """Test creating HarnessConfig."""
    llm_config = LLMConfig(provider="openai", api_key="test", model="gpt-3.5-turbo")
    config = HarnessConfig(
        llm_config=llm_config,
        dataset_path="data/problems.json",
        output_dir="output/",
        max_workers=5
    )

    assert config.max_workers == 5
    assert config.output_dir == "output/"
    assert config.dataset_path == "data/problems.json"
    assert config.log_level == "INFO"  # Default


def test_harness_config_redacted_dump_masks_api_key():
    """redacted_dump() must never leak the API key (issue #4)."""
    llm_config = LLMConfig(
        provider="openai", api_key="sk-secret-key-123", model="gpt-3.5-turbo"
    )
    config = HarnessConfig(
        llm_config=llm_config,
        dataset_path="data/problems.json",
    )

    data = config.redacted_dump()

    assert data["llm_config"]["api_key"] == "[REDACTED]"
    assert "sk-secret-key-123" not in str(data)
    # Other fields stay intact for debugging
    assert data["llm_config"]["model"] == "gpt-3.5-turbo"
    assert data["llm_config"]["provider"] == "openai"
    assert data["dataset_path"] == "data/problems.json"
    # Original config object is not mutated
    assert config.llm_config.api_key.get_secret_value() == "sk-secret-key-123"


def test_harness_config_redacted_dump_empty_key():
    """Empty API key should not gain a placeholder value."""
    llm_config = LLMConfig(provider="openai", api_key="", model="gpt-3.5-turbo")
    config = HarnessConfig(llm_config=llm_config, dataset_path="data/problems.json")

    data = config.redacted_dump()

    assert data["llm_config"]["api_key"] == ""


def test_llm_config_never_serializes_api_key_in_plaintext():
    """Configuration representations must not expose the API key."""
    secret = "issue4-fixed-secret-value"
    config = LLMConfig(provider="openai", api_key=secret, model="gpt-3.5-turbo")

    dumped = config.model_dump()

    assert secret not in repr(config)
    assert dumped["api_key"] == "[REDACTED]"
    assert secret not in yaml.dump(dumped)
    assert secret.encode() not in pickle.dumps(dumped)
    assert secret not in config.model_dump_json()


# ============================================================================
# StrategyMetrics Tests
# ============================================================================


def test_strategy_metrics_cost_estimate():
    """Test StrategyMetrics total cost estimation."""
    metrics = StrategyMetrics(
        strategy_name="vanilla",
        total_problems=100,
        successful_problems=65,
        success_rate=0.65,
        average_tokens=350.0,
        average_time_seconds=1.2,
        average_iterations=1.0,
    )

    cost = metrics.total_cost_estimate_usd
    assert cost > 0
    assert isinstance(cost, float)


def test_strategy_metrics_with_difficulty_breakdown():
    """Test StrategyMetrics with difficulty breakdown."""
    metrics = StrategyMetrics(
        strategy_name="cot",
        total_problems=100,
        successful_problems=70,
        success_rate=0.70,
        average_tokens=450.0,
        average_time_seconds=1.5,
        average_iterations=1.0,
        by_difficulty={"easy": 0.85, "medium": 0.60, "hard": 0.30},
    )

    assert metrics.by_difficulty["easy"] == 0.85
    assert metrics.by_difficulty["hard"] == 0.30


# ============================================================================
# ExecutionSummary Tests
# ============================================================================


def test_execution_summary_best_strategy():
    """Test ExecutionSummary best_strategy_by_success_rate property."""
    metrics_vanilla = StrategyMetrics(
        strategy_name="vanilla",
        total_problems=100,
        successful_problems=60,
        success_rate=0.60,
        average_tokens=300.0,
        average_time_seconds=1.0,
        average_iterations=1.0,
    )

    metrics_cot = StrategyMetrics(
        strategy_name="cot",
        total_problems=100,
        successful_problems=75,
        success_rate=0.75,
        average_tokens=450.0,
        average_time_seconds=1.5,
        average_iterations=1.0,
    )

    summary = ExecutionSummary(
        total_problems=100,
        total_strategies=2,
        metrics={"vanilla": metrics_vanilla, "cot": metrics_cot},
        report_path="report.md",
        execution_time_seconds=120.0,
    )

    assert summary.best_strategy_by_success_rate == "cot"


def test_execution_summary_most_efficient():
    """Test ExecutionSummary most_efficient_strategy property."""
    metrics_vanilla = StrategyMetrics(
        strategy_name="vanilla",
        total_problems=100,
        successful_problems=60,
        success_rate=0.60,
        average_tokens=300.0,
        average_time_seconds=1.0,
        average_iterations=1.0,
    )

    metrics_cot = StrategyMetrics(
        strategy_name="cot",
        total_problems=100,
        successful_problems=75,
        success_rate=0.75,
        average_tokens=450.0,
        average_time_seconds=1.5,
        average_iterations=1.0,
    )

    summary = ExecutionSummary(
        total_problems=100,
        total_strategies=2,
        metrics={"vanilla": metrics_vanilla, "cot": metrics_cot},
        report_path="report.md",
        execution_time_seconds=120.0,
    )

    # Vanilla uses fewer tokens but has >50% success rate
    assert summary.most_efficient_strategy == "vanilla"


def test_execution_summary_empty_metrics():
    """Test ExecutionSummary with empty metrics."""
    summary = ExecutionSummary(
        total_problems=0,
        total_strategies=1,  # At least 1 strategy required
        metrics={},
        report_path="report.md",
        execution_time_seconds=0.0,
    )

    assert summary.best_strategy_by_success_rate == ""
    assert summary.most_efficient_strategy == ""


# ============================================================================
# SandboxResult Tests
# ============================================================================


def test_sandbox_result_success():
    """Test SandboxResult for successful execution."""
    result = SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0, passed=True, actual_output=1, expected_output=1, status="passed"
            )
        ],
        execution_time=0.05,
        all_passed=True,
    )

    assert result.status == "success"
    assert result.all_passed is True


def test_sandbox_result_timeout():
    """Test SandboxResult for timeout."""
    result = SandboxResult(
        status="timeout",
        test_results=[],
        execution_time=5.0,
        all_passed=False,
        error_message="Execution timeout",
    )

    assert result.status == "timeout"
    assert result.error_message == "Execution timeout"


# ============================================================================
# TestCaseResult Tests
# ============================================================================


def test_test_case_result_passed():
    """Test TestCaseResult for passed test."""
    result = TestCaseResult(
        test_case_index=0,
        passed=True,
        actual_output=[0, 1],
        expected_output=[0, 1],
        execution_time=0.01,
        status="passed",
    )

    assert result.passed is True
    assert result.status == "passed"


def test_test_case_result_wrong_answer():
    """Test TestCaseResult for wrong answer."""
    result = TestCaseResult(
        test_case_index=0,
        passed=False,
        actual_output=[0, 0],
        expected_output=[0, 1],
        error_message="Output mismatch",
        execution_time=0.01,
        status="wrong_answer",
    )

    assert result.passed is False
    assert result.status == "wrong_answer"
    assert result.error_message == "Output mismatch"


# ============================================================================
# Result Recording Field Tests (issue #13)
# ============================================================================


def _minimal_execution_result(**overrides):
    """Build a minimal ExecutionResult with sensible defaults."""
    payload = {
        "problem_id": "test-001",
        "strategy": "vanilla",
        "generated_code": "def solution():\n    return 0",
        "status": "failed",
    }
    payload.update(overrides)
    return ExecutionResult(**payload)


def test_iteration_result_defaults_recording_fields():
    """New iteration recording fields default to empty/zero values."""
    from src.models import IterationResult

    it = IterationResult(iteration=1)

    assert it.prompt is None
    assert it.response_text is None
    assert it.llm_error is None
    assert it.sandbox_error is None
    assert it.usage_missing is False
    assert it.elapsed_seconds == 0.0


def test_iteration_result_accepts_recording_fields():
    """Iteration result stores request, response and error context."""
    from src.models import IterationResult

    it = IterationResult(
        iteration=2,
        prompt="Problem: Two Sum...",
        response_text="```python\ndef solution():\n    return 0```",
        llm_error=None,
        sandbox_error="sandbox crashed",
        usage_missing=True,
        elapsed_seconds=1.5,
    )

    assert it.prompt == "Problem: Two Sum..."
    assert "def solution" in it.response_text
    assert it.sandbox_error == "sandbox crashed"
    assert it.usage_missing is True
    assert it.elapsed_seconds == 1.5


def test_execution_result_failure_category_optional():
    """ExecutionResult carries an optional failure category."""
    result = _minimal_execution_result()
    assert result.failure_category is None

    result = _minimal_execution_result(failure_category="wrong_answer")
    assert result.failure_category == "wrong_answer"

    with pytest.raises(ValidationError):
        _minimal_execution_result(failure_category="bogus_category")


def test_strategy_report_failure_counts_default():
    """StrategyReport exposes model/system failure counters defaulting to zero."""
    report = StrategyReport(
        strategy_name="vanilla",
        total_problems=2,
        solved_problems=1,
        failed_problems=1,
        success_rate=0.5,
        avg_attempts_per_problem=1.0,
        total_tokens=100,
        avg_tokens_per_problem=50.0,
        estimated_cost_usd=0.0,
    )

    assert report.model_failed_problems == 0
    assert report.system_failed_problems == 0


def test_strategy_report_failure_counts_explicit():
    """StrategyReport accepts explicit model/system failure counters."""
    report = StrategyReport(
        strategy_name="vanilla",
        total_problems=4,
        solved_problems=1,
        failed_problems=2,
        success_rate=0.25,
        avg_attempts_per_problem=1.0,
        total_tokens=100,
        avg_tokens_per_problem=50.0,
        estimated_cost_usd=0.0,
        model_failed_problems=1,
        system_failed_problems=1,
    )

    assert report.model_failed_problems == 1
    assert report.system_failed_problems == 1
