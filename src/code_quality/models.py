"""
Code Quality Data Models

Defines all data structures for code quality evaluation metrics.
"""


from pydantic import BaseModel, Field


class TimeComplexityScore(BaseModel):
    """Time complexity analysis result."""

    static_analysis: str | None = Field(
        None, description="Inferred complexity from static analysis (e.g., 'O(n)', 'O(n^2)')"
    )
    loop_nesting_depth: int = Field(0, ge=0, description="Maximum loop nesting depth detected")
    measured_growth_rate: float | None = Field(
        None, description="Empirical growth rate from performance tests"
    )
    is_timeout: bool = Field(False, description="Whether any test exceeded timeout threshold")
    execution_times: dict[str, float] = Field(
        default_factory=dict,
        description="Execution times by scale (e.g., {'10x': 0.01, '100x': 0.1})",
    )
    performance_score: float | None = Field(
        None, ge=0.0, le=100.0, description="Overall time performance score (0-100)"
    )


class SpaceComplexityScore(BaseModel):
    """Space complexity analysis result."""

    peak_memory_bytes: int | None = Field(None, ge=0, description="Peak memory usage in bytes")
    peak_memory_mb: float | None = Field(
        None, ge=0.0, description="Peak memory usage in megabytes"
    )
    memory_efficiency_score: float | None = Field(
        None, ge=0.0, le=100.0, description="Space efficiency score (0-100)"
    )
    analysis_notes: list[str] = Field(
        default_factory=list, description="Notes about memory allocation patterns"
    )


class ReadabilityScore(BaseModel):
    """Code readability analysis result."""

    pylint_score: float | None = Field(
        None, ge=0.0, le=10.0, description="Pylint code quality score (0-10)"
    )
    flake8_issues: int | None = Field(
        None, ge=0, description="Number of flake8 style issues detected"
    )
    cyclomatic_complexity: float | None = Field(
        None, ge=1.0, description="Average cyclomatic complexity (McCabe)"
    )
    max_function_complexity: int | None = Field(
        None, ge=1, description="Maximum function complexity"
    )
    readability_score: float | None = Field(
        None, ge=0.0, le=100.0, description="Overall readability score (0-100)"
    )
    issues: list[str] = Field(
        default_factory=list, description="Specific readability issues identified"
    )


class StyleConsistencyScore(BaseModel):
    """Code style consistency analysis result."""

    black_compliant: bool | None = Field(
        None, description="Whether code passes black formatting check"
    )
    style_violations: int = Field(0, ge=0, description="Number of style violations detected")
    style_score: float | None = Field(
        None, ge=0.0, le=100.0, description="Overall style consistency score (0-100)"
    )
    violations_detail: list[str] = Field(
        default_factory=list, description="Detailed list of style violations"
    )


class CodeQualityMetrics(BaseModel):
    """Complete code quality evaluation metrics."""

    time_complexity: TimeComplexityScore | None = Field(
        None, description="Time complexity analysis results"
    )
    space_complexity: SpaceComplexityScore | None = Field(
        None, description="Space complexity analysis results"
    )
    readability: ReadabilityScore | None = Field(
        None, description="Code readability analysis results"
    )
    style_consistency: StyleConsistencyScore | None = Field(
        None, description="Code style consistency analysis results"
    )
    overall_score: float | None = Field(
        None, ge=0.0, le=100.0, description="Weighted overall quality score (0-100)"
    )
    analysis_errors: list[str] = Field(
        default_factory=list, description="Errors encountered during analysis"
    )

    def calculate_overall_score(self) -> float:
        """Calculate weighted overall quality score from individual dimensions."""
        scores = []
        weights = []

        if self.time_complexity and self.time_complexity.performance_score is not None:
            scores.append(self.time_complexity.performance_score)
            weights.append(0.3)

        if self.space_complexity and self.space_complexity.memory_efficiency_score is not None:
            scores.append(self.space_complexity.memory_efficiency_score)
            weights.append(0.2)

        if self.readability and self.readability.readability_score is not None:
            scores.append(self.readability.readability_score)
            weights.append(0.3)

        if self.style_consistency and self.style_consistency.style_score is not None:
            scores.append(self.style_consistency.style_score)
            weights.append(0.2)

        if not scores:
            return 0.0

        # Weighted average
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return round(weighted_sum / total_weight, 2)
