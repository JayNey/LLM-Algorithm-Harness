"""
LLM Algorithm Harness - Core Data Models

This module defines all Pydantic data models used throughout the system.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    field_serializer,
    field_validator,
    model_validator,
)

from src.code_quality.models import CodeQualityMetrics
from src.utils.secrets import REDACTED, redact_sensitive_data

# ============================================================================
# Problem-related Models
# ============================================================================


class TestCase(BaseModel):
    """Single test case for an algorithm problem."""

    input: Any = Field(..., description="Function parameters or raw stdin payload")
    expected_output: Any = Field(..., description="Expected output value")
    source: Literal["public", "feedback", "hidden"] = Field(
        "public", description="Test purpose and visibility"
    )
    test_case_id: Optional[str] = Field(None, description="Stable test case identifier")

    model_config = {
        "json_schema_extra": {
            "example": {
                "input": {"nums": [2, 7, 11, 15], "target": 9},
                "expected_output": [0, 1],
            }
        }
    }


class JudgeConfig(BaseModel):
    """Problem-level output comparison and stdin/stdout parsing rules."""

    comparison: Literal["exact", "float_tolerance", "unordered"] = Field(
        "float_tolerance", description="Output comparison strategy"
    )
    float_tolerance: float = Field(
        1e-6, ge=0.0, description="Absolute and relative tolerance for float comparison"
    )
    whitespace: Literal["exact", "trim", "tokens"] = Field(
        "trim", description="Whitespace policy for text stdout"
    )
    output_format: Literal["auto", "text", "json"] = Field(
        "auto", description="How stdout should be parsed"
    )


class Problem(BaseModel):
    """Algorithm problem definition."""

    problem_id: str = Field(..., min_length=1, description="Unique problem identifier")
    title: str = Field(..., min_length=1, description="Problem title")
    description: str = Field(..., min_length=10, description="Problem description")
    difficulty: Literal["easy", "medium", "hard"] = Field(..., description="Difficulty level")
    tags: List[str] = Field(default_factory=list, description="Problem tags")
    constraints: Optional[str] = Field(None, description="Problem constraints")
    schema_version: str = Field("1.1", description="Problem schema version")
    source_platform: str = Field("legacy", description="Source platform")
    source_problem_id: Optional[str] = Field(None, description="Source platform problem ID")
    source_url: Optional[str] = Field(None, description="Source problem URL")
    source_version: Optional[str] = Field(None, description="Source dataset version")
    source_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional auditable source metadata"
    )
    input_output_mode: Literal["function", "stdin_stdout"] = Field(
        "function", description="Input/output protocol"
    )
    entry_point: str = Field("solution(**test_input)", description="Execution entry signature")
    judge_config: JudgeConfig = Field(
        default_factory=JudgeConfig, description="Problem-level judge configuration"
    )
    unsupported_reason: Optional[str] = Field(
        None, description="Explicit reason when this problem type is unsupported"
    )
    needs_manual_completion: bool = Field(
        False, description="Whether imported metadata or public samples need manual completion"
    )
    manual_completion_notes: List[str] = Field(
        default_factory=list, description="Reasons and fields that need manual completion"
    )
    public_test_cases: List[TestCase] = Field(
        default_factory=list, description="Public examples visible to the model"
    )
    feedback_test_cases: List[TestCase] = Field(
        default_factory=list, description="Tests allowed for iterative feedback"
    )
    hidden_test_cases: List[TestCase] = Field(
        default_factory=list, description="Tests reserved for final evaluation"
    )
    migration_status: Literal["native", "legacy_test_cases_as_public"] = Field(
        "native", description="How the problem entered the current schema"
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_test_cases(cls, data: Any) -> Any:
        """Move legacy test_cases to public examples without inferring hidden tests."""
        if not isinstance(data, dict):
            return data
        values = dict(data)
        legacy_cases = values.pop("test_cases", None)
        if legacy_cases is not None:
            if any(
                key in values
                for key in ("public_test_cases", "feedback_test_cases", "hidden_test_cases")
            ):
                raise ValueError("Use test_cases or the staged test lists, not both")
            values["public_test_cases"] = legacy_cases
            values["migration_status"] = "legacy_test_cases_as_public"
        return values

    @model_validator(mode="after")
    def assign_test_case_sources(self) -> "Problem":
        """Ensure each staged list carries its authoritative visibility label."""
        self.public_test_cases = [
            case.model_copy(update={"source": "public"}) for case in self.public_test_cases
        ]
        self.feedback_test_cases = [
            case.model_copy(update={"source": "feedback"}) for case in self.feedback_test_cases
        ]
        self.hidden_test_cases = [
            case.model_copy(update={"source": "hidden"}) for case in self.hidden_test_cases
        ]
        if (
            not self.public_test_cases
            and not self.feedback_test_cases
            and not self.hidden_test_cases
            and not self.needs_manual_completion
        ):
            raise ValueError("At least one public, feedback, or hidden test case is required")
        return self

    @property
    def test_cases(self) -> List[TestCase]:
        """Backward-compatible public test list; hidden cases are never included."""
        return self.public_test_cases

    def test_cases_for(self, stage: str = "public") -> List[TestCase]:
        """Return only tests for an explicit execution stage."""
        stages = {
            "public": self.public_test_cases,
            "feedback": self.feedback_test_cases,
            "hidden": self.hidden_test_cases,
            "all_visible": self.public_test_cases + self.feedback_test_cases,
            "all": self.public_test_cases + self.feedback_test_cases + self.hidden_test_cases,
        }
        if stage not in stages:
            raise ValueError(f"Unknown test stage: {stage}")
        return stages[stage]

    @property
    def formal_evaluable(self) -> bool:
        """Whether an independent hidden score can be produced for this problem."""
        return bool(self.hidden_test_cases) and not self.unsupported_reason

    def prompt_view(self) -> Dict[str, Any]:
        """Return problem context that excludes feedback and hidden test contents."""
        return {
            "schema_version": self.schema_version,
            "problem_id": self.problem_id,
            "title": self.title,
            "description": self.description,
            "difficulty": self.difficulty,
            "tags": list(self.tags),
            "constraints": self.constraints,
            "source_platform": self.source_platform,
            "source_problem_id": self.source_problem_id,
            "source_url": self.source_url,
            "source_version": self.source_version,
            "source_metadata": dict(self.source_metadata),
            "input_output_mode": self.input_output_mode,
            "entry_point": self.entry_point,
            "judge_config": self.judge_config.model_dump(mode="json"),
            "unsupported_reason": self.unsupported_reason,
            "needs_manual_completion": self.needs_manual_completion,
            "manual_completion_notes": list(self.manual_completion_notes),
            "test_cases": [case.model_dump(mode="json") for case in self.public_test_cases],
        }

    def validate_completeness(self) -> bool:
        """Validate problem data completeness."""
        return (
            bool(self.problem_id)
            and bool(self.title)
            and bool(self.description)
            and (
                len(self.public_test_cases)
                + len(self.feedback_test_cases)
                + len(self.hidden_test_cases)
                > 0
                or self.needs_manual_completion
            )
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
        "success",
        "failed",
        "timeout",
        "memory_error",
        "syntax_error",
        "runtime_error",
        "backend_unavailable",
        "output_limit",
        "process_limit",
        "sandbox_error",
        "unsupported",
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
    prompt: Optional[str] = Field(None, description="Redacted request prompt sent to the model")
    response_text: Optional[str] = Field(
        None, description="Raw model response text (redacted before persisting)"
    )
    llm_error: Optional[str] = Field(
        None, description="Redacted model API error for this iteration"
    )
    sandbox_error: Optional[str] = Field(
        None, description="Redacted sandbox failure reason for this iteration"
    )
    reflection_text: Optional[str] = Field(
        None, description="Redacted reflection generated after a visible failure"
    )
    reflection_error: Optional[str] = Field(
        None, description="Redacted error from the optional reflection call"
    )
    reflection_prompt_tokens: int = Field(0, ge=0, description="Reflection prompt tokens used")
    reflection_completion_tokens: int = Field(
        0, ge=0, description="Reflection completion tokens used"
    )
    reflection_usage_missing: bool = Field(
        False, description="True when the reflection provider response had no usage data"
    )
    reflection_pricing_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Pricing metadata for the reflection call"
    )
    reflection_reasoning_text: Optional[str] = Field(
        None, description="Redacted provider reasoning from the reflection call"
    )
    usage_missing: bool = Field(False, description="True when the provider returned no usage data")
    effective_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Redacted model parameters effective for this iteration",
    )
    elapsed_seconds: float = Field(0.0, ge=0, description="Wall-clock duration of this iteration")


class ExecutionResult(BaseModel):
    """Complete result of strategy execution on a problem."""

    problem_id: str = Field(..., description="Problem ID")
    strategy: str = Field(..., description="Strategy name")
    generated_code: str = Field(..., description="Generated code")
    status: str = Field(..., description="Execution status")
    evaluation_completed: bool = Field(
        True,
        description="False for a task-service placeholder when no execution result was recorded",
    )
    failure_category: Optional[
        Literal[
            "wrong_answer",
            "code_extraction_failed",
            "model_error",
            "system_error",
            "unsupported",
            "budget_exhausted",
        ]
    ] = Field(
        None,
        description=(
            "Failure classification; None for successful runs. Kept separate "
            "from status so existing status consumers stay compatible"
        ),
    )
    failure_mode: Optional[
        Literal[
            "syntax_error",
            "logic_error",
            "timeout",
            "boundary_condition",
            "understanding_error",
            "runtime_error",
            "infrastructure_error",
            "unknown",
        ]
    ] = Field(None, description="Evidence-based detailed failure mode for this completed result")
    failure_mode_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Rule confidence, not calibrated probability"
    )
    failure_mode_evidence: List[str] = Field(
        default_factory=list, description="Non-sensitive rule identifiers supporting the mode"
    )
    difficulty: Optional[Literal["easy", "medium", "hard"]] = Field(
        None, description="Problem difficulty level"
    )
    iterations: List[IterationResult] = Field(default_factory=list, description="Iteration results")
    final_result: Optional[SandboxResult] = Field(None, description="Final sandbox result")
    hidden_result: Optional[SandboxResult] = Field(
        None, description="Independent hidden evaluation result"
    )
    formal_evaluable: bool = Field(
        False, description="Whether this problem has independent hidden evaluation cases"
    )
    test_results: List[TestCaseResult] = Field(default_factory=list, description="Test results")
    error_message: Optional[str] = Field(None, description="Error message")
    total_tokens: int = Field(0, ge=0, description="Total tokens used")
    execution_time_seconds: float = Field(0.0, ge=0, description="Execution time")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="Timestamp"
    )
    llm_traces: List[Dict[str, Any]] = Field(
        default_factory=list, description="LLM interaction traces"
    )
    cost_downgraded: bool = Field(
        False,
        description="True when the run-level budget cap downgraded this problem to a cheaper strategy",
    )
    quality_metrics: Optional["CodeQualityMetrics"] = Field(
        None, description="Code quality evaluation metrics"
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
        description="Pricing information used for cost estimation (model, prompt_price_per_1k, completion_price_per_1k, source)",
    )
    by_difficulty: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Success rate breakdown by difficulty level"
    )
    model_failed_problems: int = Field(
        0, ge=0, description="Problems that failed because the model API errored"
    )
    system_failed_problems: int = Field(
        0, ge=0, description="Problems that failed because of harness/system errors"
    )
    formal_evaluable_problems: int = Field(
        0, ge=0, description="Problems with independent hidden evaluation cases"
    )
    sample_only_problems: int = Field(
        0, ge=0, description="Problems that only have public/feedback tests"
    )
    formal_solved_problems: int = Field(
        0, ge=0, description="Formally evaluated problems solved by hidden tests"
    )
    formal_success_rate: float = Field(
        0.0, ge=0.0, le=1.0, description="Success rate over formal hidden evaluations"
    )


# ============================================================================
# LLM-related Models
# ============================================================================


class TokenUsage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = Field(..., ge=0, description="Input tokens")
    completion_tokens: int = Field(..., ge=0, description="Output tokens")
    total_tokens: int = Field(..., ge=0, description="Total tokens")
    reasoning_tokens: int = Field(
        0,
        ge=0,
        description=(
            "Reasoning tokens reported by the provider; already included in "
            "the completion and total counts, tracked separately for budgets"
        ),
    )

    @property
    def cost_estimate_usd(self) -> Decimal:
        """Estimate cost in USD with precise decimal arithmetic."""
        INPUT_PRICE_PER_1K = Decimal("0.0005")
        OUTPUT_PRICE_PER_1K = Decimal("0.0015")

        return (
            Decimal(str(self.prompt_tokens)) * INPUT_PRICE_PER_1K / 1000
            + Decimal(str(self.completion_tokens)) * OUTPUT_PRICE_PER_1K / 1000
        )


class LLMResponse(BaseModel):
    """LLM API response."""

    text: str = Field(..., description="Generated text")
    usage: TokenUsage = Field(..., description="Token usage")
    model: str = Field(..., description="Model name")
    finish_reason: Optional[str] = Field(None, description="Finish reason")
    pricing_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Pricing information used for cost estimation"
    )
    usage_missing: bool = Field(
        False,
        description="True when the provider response carried no usage data",
    )
    reasoning_text: Optional[str] = Field(
        None,
        description="Optional provider reasoning content kept separate from answer text",
    )
    effective_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Redacted request parameters used for this response",
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


class CacheConfig(BaseModel):
    """Cache configuration for LLM responses."""

    enabled: bool = Field(True, description="Whether caching is enabled")
    backend: Literal["disk"] = Field("disk", description="Cache storage backend")
    ttl_days: int = Field(30, ge=1, description="Cache entry time-to-live in days")
    max_size_mb: int = Field(1000, ge=1, description="Maximum cache size in MB")


class LLMConfig(BaseModel):
    """LLM client configuration."""

    provider: Literal["openai", "anthropic", "local", "siliconflow"] = Field(
        ..., description="Provider type"
    )
    api_key: SecretStr = Field(..., description="API key or environment reference")
    model: str = Field(..., description="Model name")
    base_url: Optional[str] = Field(None, description="Base URL for local models")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(2000, ge=1, le=8000, description="Max generation tokens")
    timeout: int = Field(30, ge=1, description="Request timeout in seconds")
    enable_thinking: Optional[bool] = Field(
        None, description="Toggle thinking mode for reasoning models (e.g. SiliconFlow Qwen3.5)"
    )
    retry_max_attempts: int = Field(
        3,
        ge=1,
        le=5,
        description="Maximum total attempts for retryable provider errors",
    )
    retry_backoff_seconds: float = Field(
        0.5,
        ge=0.0,
        le=60.0,
        description="Initial delay between retry attempts",
    )
    retry_max_elapsed_seconds: float = Field(
        60.0,
        ge=0.0,
        le=600.0,
        description="Maximum wall-clock time spent retrying one request",
    )
    cache: CacheConfig = Field(
        default_factory=CacheConfig, description="Cache configuration"
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

    backend: Literal["docker", "host"] = Field(
        "docker", description="Isolation backend; host is intended for tests only"
    )
    docker_image: str = Field("python:3.11-slim", description="Docker image for isolated execution")
    timeout_seconds: int = Field(5, ge=1, le=60, description="Timeout per test case")
    memory_limit_mb: int = Field(256, ge=64, le=2048, description="Memory limit in MB")
    max_output_bytes: int = Field(1_000_000, ge=1024, le=10_000_000)
    max_processes: int = Field(16, ge=1, le=256)
    allowed_imports: List[str] = Field(
        default_factory=lambda: [
            "math",
            "itertools",
            "collections",
            "heapq",
            "bisect",
            "functools",
            "sys",
            "json",
        ],
        description="Allowed import modules",
    )


class StrategyConfig(BaseModel):
    """Strategy configuration."""

    name: str = Field(..., description="Strategy name")
    max_iterations: int = Field(1, ge=1, le=10, description="Max iterations")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="LLM temperature")
    max_tokens: int = Field(2000, ge=100, le=8000, description="Max tokens per generation")
    system_prompt: Optional[str] = Field(None, description="System prompt override")
    custom_params: Dict[str, Any] = Field(default_factory=dict, description="Custom parameters")


class ProblemBudget(BaseModel):
    """Per-problem budget caps for fixed-budget experiments.

    Each problem starts with a fresh budget. Token budgets settle against
    known provider usage only (input + output, including any reasoning
    tokens the provider reports inside its completion count).
    """

    max_calls: Optional[int] = Field(None, ge=1, description="Maximum model calls per problem")
    max_tokens: Optional[int] = Field(
        None,
        ge=1,
        description="Maximum known token usage per problem before the next call is refused",
    )
    max_seconds: Optional[float] = Field(
        None, gt=0, description="Maximum wall-clock seconds per problem"
    )


class ExperimentConfig(BaseModel):
    """Fixed-budget experiment configuration (model x strategy x dataset x repeat)."""

    name: Optional[str] = Field(None, description="Human-readable experiment name")
    dataset_path: str = Field(..., description="Path to the problem dataset JSON file")
    output_dir: str = Field(
        "./results/experiments", description="Base output directory for experiment artifacts"
    )
    models: List[LLMConfig] = Field(
        ..., min_length=1, description="Model configurations to compare"
    )
    strategies: List[StrategyConfig] = Field(
        ..., min_length=1, description="Strategy configurations to compare"
    )
    repeats: int = Field(
        1, ge=1, description="Number of repetitions per model x strategy combination"
    )
    budget: Optional[ProblemBudget] = Field(
        None, description="Optional per-problem budget caps applied to every combination"
    )
    execution: Literal["serial", "parallel"] = Field(
        "serial",
        description=(
            "Combination execution mode; parallel runs combinations concurrently, "
            "each with its own harness and budget tracker"
        ),
    )
    max_workers: int = Field(
        4,
        ge=1,
        le=16,
        description="Upper bound of concurrently executed combinations in parallel mode",
    )
    sandbox_config: SandboxConfig = Field(
        default_factory=SandboxConfig, description="Sandbox configuration"
    )
    problem_filters: Optional[Dict[str, Any]] = Field(
        None, description="Optional filters applied to the dataset before execution"
    )

    def redacted_dict(self) -> Dict[str, Any]:
        """Return a serialization-safe view of the experiment configuration."""
        return redact_sensitive_data(self.model_dump(mode="json"))


class CostAlertConfig(BaseModel):
    """Run-level cost alert delivery settings. Endpoints are credentials."""

    thresholds: List[int] = Field(
        default_factory=lambda: [50, 80, 90],
        description="Budget percentages that trigger one alert each",
    )
    slack_webhook_url: Optional[SecretStr] = None
    webhook_url: Optional[SecretStr] = None
    smtp_host: Optional[str] = None
    smtp_port: int = Field(587, ge=1, le=65535)
    smtp_username: Optional[str] = None
    smtp_password: Optional[SecretStr] = None
    smtp_from: Optional[str] = None
    smtp_to: List[str] = Field(default_factory=list)
    smtp_use_starttls: bool = True
    timeout_seconds: float = Field(5.0, gt=0, le=60)
    max_retries: int = Field(2, ge=0, le=5)

    @field_validator("thresholds")
    @classmethod
    def validate_thresholds(cls, value: List[int]) -> List[int]:
        if not value or any(type(item) is not int or item < 1 or item > 99 for item in value):
            raise ValueError("cost alert thresholds must be integer percentages from 1 to 99")
        if len(set(value)) != len(value):
            raise ValueError("cost alert thresholds must be unique")
        return sorted(value)

    @model_validator(mode="after")
    def validate_delivery(self) -> "CostAlertConfig":
        for endpoint in (self.slack_webhook_url, self.webhook_url):
            if endpoint is not None:
                parsed = urlparse(endpoint.get_secret_value())
                if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                    raise ValueError("webhook URLs must be HTTPS URLs without embedded credentials")
        smtp_fields = (self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_from, self.smtp_to)
        if any(smtp_fields):
            if not self.smtp_host or not self.smtp_from or not self.smtp_to:
                raise ValueError("SMTP delivery requires smtp_host, smtp_from and smtp_to")
            if self.smtp_username and (
                self.smtp_password is None or not self.smtp_password.get_secret_value()
            ):
                raise ValueError("SMTP authentication requires smtp_password")
            if self.smtp_username and not self.smtp_use_starttls:
                raise ValueError("SMTP authentication requires STARTTLS")
            if any("\r" in address or "\n" in address for address in [self.smtp_from, *self.smtp_to]):
                raise ValueError("SMTP addresses must not contain line breaks")
        return self


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
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field("INFO", description="Log level")
    problem_filters: Optional[Dict[str, Any]] = Field(
        None, description="Optional filters for problems (difficulty, tags, etc.)"
    )
    difficulty_strategy: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Cost-aware difficulty to strategy mapping (easy/medium/hard); "
            "when set, each problem runs once with its mapped strategy"
        ),
    )
    budget_cap_usd: Optional[float] = Field(
        None,
        gt=0,
        allow_inf_nan=False,
        description="Run-level known cost cap in USD",
    )
    budget_action: Optional[Literal["auto_stop", "downgrade"]] = Field(
        None, description="Action at the run-level cost cap; selector runs default to downgrade"
    )
    cost_alerts: Optional[CostAlertConfig] = Field(
        None, description="Thresholds and notification channels for run-level cost alerts"
    )
    enable_quality_analysis: bool = Field(
        False, description="Enable code quality analysis (time/space complexity, readability, style)"
    )
    quality_analysis_config: Optional[Dict[str, bool]] = Field(
        None,
        description="Fine-grained quality analysis toggles: enable_time_analysis, enable_space_analysis, enable_readability_analysis, enable_style_analysis",
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
    def total_cost_estimate_usd(self) -> Decimal:
        """Estimate total cost in USD with precise decimal arithmetic."""
        INPUT_PRICE_PER_1K = Decimal("0.0005")
        OUTPUT_PRICE_PER_1K = Decimal("0.0015")
        avg_input = Decimal(str(self.average_tokens)) * Decimal("0.4")
        avg_output = Decimal(str(self.average_tokens)) * Decimal("0.6")

        return (
            avg_input * INPUT_PRICE_PER_1K / 1000 + avg_output * OUTPUT_PRICE_PER_1K / 1000
        ) * Decimal(str(self.total_problems))


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
            name: metrics for name, metrics in self.metrics.items() if metrics.success_rate > 0.5
        }
        if not eligible:
            return ""
        return min(eligible.items(), key=lambda x: x[1].average_tokens)[0]
