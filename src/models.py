"""
LLM Algorithm Harness - Core Data Models

This module defines all Pydantic data models used throughout the system.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, SecretStr, field_serializer, field_validator

from src.utils.secrets import REDACTED, redact_sensitive_data


# ============================================================================
# Problem-related Models
# ============================================================================


class TestCase(BaseModel):
    """Single test case for an algorithm problem."""

    input: Dict[str, Any] = Field(..., description="Test input parameters")
    expected_output: Any = Field(..., description="Expected output value")

    model_config = {
        "json_schema_extra": {
            "example": {
                "input": {"nums": [2, 7, 11, 15], "target": 9},
                "expected_output": [0, 1],
            }
        }
    }


class Problem(BaseModel):
    """Algorithm problem definition."""

    problem_id: str = Field(..., min_length=1, description="Unique problem identifier")
    title: str = Field(..., min_length=1, description="Problem title")
    description: str = Field(..., min_length=10, description="Problem description")
    difficulty: Literal["easy", "medium", "hard"] = Field(..., description="Difficulty level")
    tags: List[str] = Field(default_factory=list, description="Problem tags")
    test_cases: List[TestCase] = Field(..., min_length=1, description="Test cases")
    constraints: Optional[str] = Field(None, description="Problem constraints")

    @field_validator("test_cases")
    @classmethod
    def test_cases_not_empty(cls, v: List[TestCase]) -> List[TestCase]:
        """Ensure at least one test case exists."""
        if len(v) == 0:
            raise ValueError("test_cases must contain at least one test case")
        return v

    def validate_completeness(self) -> bool:
        """Validate problem data completeness."""
        return (
            bool(self.problem_id)
            and bool(self.title)
            and bool(self.description)
            and len(self.test_cases) > 0
            and self.difficulty in ["easy", "medium", "hard"]
        )

    model_config = {
        "json_schema_extra": {
            "example": {
                "problem_id": "leetcode-001",
                "title": "Two Sum",
                "description": "Given an array of integers nums...",
                "difficulty": "easy",
                "tags": ["array", "hash-table"],
                "test_cases": [
                    {"input": {"nums": [2, 7, 11, 15], "target": 9}, "expected_output": [0, 1]}
                ],
                "constraints": "2 <= nums.length <= 10^4",
            }
        }
    }


# ============================================================================
# Execution-related Models
# ============================================================================


class TestCaseResult(BaseModel):
    """Result of executing a single test case."""

    test_case_index: int = Field(..., ge=0, description="Test case index")
    passed: bool = Field(..., description="Whether test passed")
    actual_output: Any = Field(None, description="Actual output")
    expected_output: Any = Field(None, description="Expected output")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    execution_time: float = Field(0.0, ge=0, description="Execution time in seconds")
    status: str = Field(
        "unknown", description="Status: passed, wrong_answer, timeout, runtime_error"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "test_case_index": 0,
                "passed": True,
                "actual_output": [0, 1],
                "expected_output": [0, 1],
                "error_message": None,
                "execution_time": 0.002,
                "status": "passed",
            }
        }
    }


class SandboxResult(BaseModel):
    """Aggregated result of sandbox execution."""

    status: Literal[
        "success", "failed", "timeout", "memory_error", "syntax_error", "runtime_error"
    ] = Field(..., description="Execution status")
    test_results: List[TestCaseResult] = Field(
        default_factory=list, description="Individual test results"
    )
    execution_time: float = Field(0.0, ge=0, description="Total execution time")
    all_passed: bool = Field(False, description="Whether all tests passed")
    error_message: Optional[str] = Field(None, description="Global error message")


class IterationResult(BaseModel):
    """Result of a single strategy iteration (for multi-round strategies)."""

    iteration: int = Field(..., ge=1, description="Iteration number")
    prompt_tokens: int = Field(0, ge=0, description="Prompt tokens used")
    completion_tokens: int = Field(0, ge=0, description="Completion tokens used")
    code_extracted: Optional[str] = Field(None, description="Extracted code")
    sandbox_result: Optional[SandboxResult] = Field(None, description="Sandbox execution result")
    prompt: Optional[str] = Field(
        None, description="Redacted request prompt sent to the model"
    )
    response_text: Optional[str] = Field(
        None, description="Raw model response text (redacted before persisting)"
    )
    llm_error: Optional[str] = Field(
        None, description="Redacted model API error for this iteration"
    )
    sandbox_error: Optional[str] = Field(
        None, description="Redacted sandbox failure reason for this iteration"
    )
    usage_missing: bool = Field(
        False, description="True when the provider returned no usage data"
    )
    elapsed_seconds: float = Field(
        0.0, ge=0, description="Wall-clock duration of this iteration"
    )


class ExecutionResult(BaseModel):
    """Complete result of strategy execution on a problem."""

    problem_id: str = Field(..., description="Problem ID")
    strategy: str = Field(..., description="Strategy name")
    generated_code: str = Field(..., description="Generated code")
    status: str = Field(..., description="Execution status")
    failure_category: Optional[
        Literal["wrong_answer", "code_extraction_failed", "model_error", "system_error"]
    ] = Field(
        None,
        description=(
            "Failure classification; None for successful runs. Kept separate "
            "from status so existing status consumers stay compatible"
        ),
    )
    iterations: List[IterationResult] = Field(
        default_factory=list, description="Iteration results"
    )
    final_result: Optional[SandboxResult] = Field(None, description="Final sandbox result")
    test_results: List[TestCaseResult] = Field(
        default_factory=list, description="Test results"
    )
    error_message: Optional[str] = Field(None, description="Error message")
    total_tokens: int = Field(0, ge=0, description="Total tokens used")
    execution_time_seconds: float = Field(0.0, ge=0, description="Execution time")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="Timestamp"
    )
    llm_traces: List[Dict[str, Any]] = Field(
        default_factory=list, description="LLM interaction traces"
    )

    @property
    def success(self) -> bool:
        """Whether the execution was successful."""
        return self.status == "success"

    def is_successful(self) -> bool:
        """Check if execution was successful."""
        return self.status == "success" and all(tc.passed for tc in self.test_results)


class StrategyReport(BaseModel):
    """Aggregated report for a strategy across multiple problems."""

    strategy_name: str = Field(..., description="Strategy name")
    total_problems: int = Field(..., ge=0, description="Total problems attempted")
    solved_problems: int = Field(..., ge=0, description="Number of problems solved")
    failed_problems: int = Field(..., ge=0, description="Number of problems failed")
    success_rate: float = Field(..., ge=0.0, le=1.0, description="Success rate (0.0-1.0)")
    avg_attempts_per_problem: float = Field(..., ge=0.0, description="Average attempts per problem")
    total_tokens: int = Field(..., ge=0, description="Total tokens used")
    avg_tokens_per_problem: float = Field(..., ge=0.0, description="Average tokens per problem")
    estimated_cost_usd: float = Field(..., ge=0.0, description="Estimated cost in USD")
    pricing_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Pricing information used for cost estimation (model, prompt_price_per_1k, completion_price_per_1k, source)"
    )
    by_difficulty: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Success rate breakdown by difficulty level"
    )
    model_failed_problems: int = Field(
        0, ge=0, description="Problems that failed because the model API errored"
    )
    system_failed_problems: int = Field(
        0, ge=0, description="Problems that failed because of harness/system errors"
    )


# ============================================================================
# LLM-related Models
# ============================================================================


class TokenUsage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = Field(..., ge=0, description="Input tokens")
    completion_tokens: int = Field(..., ge=0, description="Output tokens")
    total_tokens: int = Field(..., ge=0, description="Total tokens")

    @property
    def cost_estimate_usd(self) -> float:
        """Estimate cost in USD (based on GPT-3.5 pricing)."""
        INPUT_PRICE_PER_1K = 0.0005
        OUTPUT_PRICE_PER_1K = 0.0015

        return (
            self.prompt_tokens * INPUT_PRICE_PER_1K / 1000
            + self.completion_tokens * OUTPUT_PRICE_PER_1K / 1000
        )


class LLMResponse(BaseModel):
    """LLM API response."""

    text: str = Field(..., description="Generated text")
    usage: TokenUsage = Field(..., description="Token usage")
    model: str = Field(..., description="Model name")
    finish_reason: Optional[str] = Field(None, description="Finish reason")
    pricing_metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Pricing information used for cost estimation"
    )
    usage_missing: bool = Field(
        False,
        description="True when the provider response carried no usage data",
    )


class ProviderResponse(BaseModel):
    """Unified provider response format."""

    text: str = Field(..., description="Generated text")
    model: str = Field(..., description="Model used")
    usage: TokenUsage = Field(..., description="Token usage")
    finish_reason: Optional[str] = Field(None, description="Finish reason")
    raw_response: Optional[Dict[str, Any]] = Field(None, description="Raw response")


# ============================================================================
# Configuration Models
# ============================================================================


class LLMConfig(BaseModel):
    """LLM client configuration."""

    provider: Literal["openai", "anthropic", "local"] = Field(..., description="Provider type")
    api_key: SecretStr = Field(..., description="API key or environment reference")
    model: str = Field(..., description="Model name")
    base_url: Optional[str] = Field(None, description="Base URL for local models")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(2000, ge=1, le=8000, description="Max generation tokens")
    timeout: int = Field(30, ge=1, description="Request timeout in seconds")
    enable_thinking: Optional[bool] = Field(
        None, description="Toggle thinking mode for reasoning models (e.g. SiliconFlow Qwen3.5)"
    )

    @field_serializer("api_key", when_used="always")
    def serialize_api_key(self, value: SecretStr) -> str:
        """Never place the underlying key into model dumps."""
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        return REDACTED if raw_value else ""

    def redacted_dict(self) -> Dict[str, Any]:
        """Return a serialization-safe view of the model configuration."""
        return redact_sensitive_data(self.model_dump(mode="json"))


class SandboxConfig(BaseModel):
    """Sandbox executor configuration."""

    timeout_seconds: int = Field(5, ge=1, le=60, description="Timeout per test case")
    memory_limit_mb: int = Field(256, ge=64, le=2048, description="Memory limit in MB")
    allowed_imports: List[str] = Field(
        default_factory=lambda: ["math", "itertools", "collections", "heapq", "bisect", "functools"],
        description="Allowed import modules",
    )


class StrategyConfig(BaseModel):
    """Strategy configuration."""

    name: str = Field(..., description="Strategy name")
    max_iterations: int = Field(1, ge=1, le=10, description="Max iterations")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="LLM temperature")
    max_tokens: int = Field(2000, ge=100, le=8000, description="Max tokens per generation")
    system_prompt: Optional[str] = Field(None, description="System prompt override")
    custom_params: Dict[str, Any] = Field(
        default_factory=dict, description="Custom parameters"
    )


class HarnessConfig(BaseModel):
    """Overall harness configuration."""

    llm_config: LLMConfig = Field(..., description="LLM configuration")
    sandbox_config: SandboxConfig = Field(
        default_factory=SandboxConfig, description="Sandbox configuration"
    )
    dataset_path: str = Field(..., description="Path to problem dataset directory or JSON file")
    strategies: List["StrategyConfig"] = Field(
        default_factory=list, description="List of strategy configurations"
    )
    output_dir: str = Field("./results", description="Output directory")
    max_workers: int = Field(5, ge=1, le=20, description="Number of parallel workers")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        "INFO", description="Log level"
    )
    problem_filters: Optional[Dict[str, Any]] = Field(
        None, description="Optional filters for problems (difficulty, tags, etc.)"
    )

    def redacted_dump(self) -> Dict[str, Any]:
        """Compatibility alias for callers using the original safe dump API."""
        return self.redacted_dict()

    def redacted_dict(self) -> Dict[str, Any]:
        """Return a recursively redacted configuration snapshot."""
        return redact_sensitive_data(self.model_dump(mode="json"))


# ============================================================================
# Metrics Models
# ============================================================================


class StrategyMetrics(BaseModel):
    """Aggregated metrics for a strategy."""

    strategy_name: str = Field(..., description="Strategy name")
    total_problems: int = Field(..., ge=0, description="Total problems")
    successful_problems: int = Field(..., ge=0, description="Successful problems")
    success_rate: float = Field(..., ge=0.0, le=1.0, description="Success rate")
    average_tokens: float = Field(..., ge=0, description="Average tokens")
    average_time_seconds: float = Field(..., ge=0, description="Average time")
    average_iterations: float = Field(..., ge=1, description="Average iterations")
    token_percentiles: Dict[str, float] = Field(
        default_factory=dict, description="Token percentiles"
    )
    by_difficulty: Dict[str, float] = Field(
        default_factory=dict, description="Success rate by difficulty"
    )

    @property
    def total_cost_estimate_usd(self) -> float:
        """Estimate total cost in USD."""
        INPUT_PRICE_PER_1K = 0.0005
        OUTPUT_PRICE_PER_1K = 0.0015
        avg_input = self.average_tokens * 0.4
        avg_output = self.average_tokens * 0.6

        return (
            avg_input * INPUT_PRICE_PER_1K / 1000 + avg_output * OUTPUT_PRICE_PER_1K / 1000
        ) * self.total_problems


class ComparisonResult(BaseModel):
    """Strategy comparison result."""

    strategy_a: str = Field(..., description="Strategy A name")
    strategy_b: str = Field(..., description="Strategy B name")
    success_rate_diff: float = Field(..., description="Success rate difference (A - B)")
    success_rate_pvalue: float = Field(..., ge=0.0, le=1.0, description="P-value")
    token_diff: float = Field(..., description="Token difference (A - B)")
    token_pvalue: float = Field(..., ge=0.0, le=1.0, description="Token p-value")
    is_significant: bool = Field(..., description="Is difference significant (p < 0.05)")
    summary: str = Field(..., description="Comparison summary")


class ExecutionSummary(BaseModel):
    """Execution summary."""

    total_problems: int = Field(..., ge=0, description="Total problems")
    total_strategies: int = Field(..., ge=1, description="Total strategies")
    metrics: Dict[str, StrategyMetrics] = Field(..., description="Strategy metrics")
    report_path: str = Field(..., description="Report file path")
    execution_time_seconds: float = Field(..., ge=0, description="Total execution time")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="Timestamp"
    )

    @property
    def best_strategy_by_success_rate(self) -> str:
        """Get strategy with highest success rate."""
        if not self.metrics:
            return ""
        return max(self.metrics.items(), key=lambda x: x[1].success_rate)[0]

    @property
    def most_efficient_strategy(self) -> str:
        """Get most token-efficient strategy (among those with >50% success)."""
        eligible = {
            name: metrics
            for name, metrics in self.metrics.items()
            if metrics.success_rate > 0.5
        }
        if not eligible:
            return ""
        return min(eligible.items(), key=lambda x: x[1].average_tokens)[0]
