"""
Unit tests for MarkdownGenerator.
"""

from pathlib import Path
from typing import Dict, List

import pytest

from src.models import ExecutionResult, TestCaseResult
from src.reporting.markdown_generator import MarkdownGenerator


@pytest.fixture
def temp_md_path(tmp_path: Path) -> str:
    """Fixture for temporary Markdown file path."""
    return str(tmp_path / "test_report.md")


@pytest.fixture
def sample_metrics() -> Dict[str, Dict]:
    """Fixture for sample strategy metrics."""
    return {
        "direct": {
            "total_problems": 10,
            "solved_problems": 8,
            "success_rate": 0.8,
            "avg_tokens_per_problem": 500.0,
            "avg_time_per_problem": 1.5,
            "by_difficulty": {
                "easy": {"total": 5, "solved": 5, "success_rate": 1.0},
                "medium": {"total": 3, "solved": 2, "success_rate": 0.67},
                "hard": {"total": 2, "solved": 1, "success_rate": 0.5}
            }
        },
        "cot": {
            "total_problems": 10,
            "solved_problems": 9,
            "success_rate": 0.9,
            "avg_tokens_per_problem": 800.0,
            "avg_time_per_problem": 2.0,
            "by_difficulty": {
                "easy": {"total": 5, "solved": 5, "success_rate": 1.0},
                "medium": {"total": 3, "solved": 3, "success_rate": 1.0},
                "hard": {"total": 2, "solved": 1, "success_rate": 0.5}
            }
        }
    }


@pytest.fixture
def sample_results() -> Dict[str, List[ExecutionResult]]:
    """Fixture for sample execution results."""
    passed_result = ExecutionResult(
        problem_id="problem_1",
        strategy="direct",
        generated_code="def solution(): pass",
        status="success",
        iterations=[],
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0],
                expected_output=[0],
                execution_time=0.01,
                status="passed"
            )
        ],
        total_tokens=100,
        execution_time_seconds=0.5
    )

    failed_result = ExecutionResult(
        problem_id="problem_2",
        strategy="direct",
        generated_code="def solution(): pass",
        status="failed",
        iterations=[],
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=False,
                actual_output=[],
                expected_output=[0],
                execution_time=0.01,
                status="failed"
            )
        ],
        error_message="Test failed",
        total_tokens=100,
        execution_time_seconds=0.5
    )

    return {
        "direct": [passed_result, failed_result],
        "cot": [passed_result]
    }


def test_generate_creates_file(temp_md_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that generate creates a Markdown file."""
    MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path)

    assert Path(temp_md_path).exists()


def test_generate_contains_header(temp_md_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that generated Markdown contains proper header."""
    content = MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path)

    assert "# LLM Algorithm Harness - Evaluation Report" in content
    assert "**Generated:**" in content


def test_generate_contains_summary_table(temp_md_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that generated Markdown contains strategy summary table."""
    content = MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path)

    assert "## Strategy Performance Summary" in content
    assert "| Strategy | Success Rate | Solved | Total | Avg Tokens | Avg Time (s) |" in content
    assert "direct" in content
    assert "cot" in content
    assert "80.0%" in content
    assert "90.0%" in content


def test_generate_sorts_by_success_rate(temp_md_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that strategies are sorted by success rate (descending)."""
    content = MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path)

    lines = content.split('\n')
    table_start = next(i for i, line in enumerate(lines) if '| Strategy |' in line)

    # Find the first strategy row (skip header and separator)
    first_strategy_row = lines[table_start + 2]

    # cot has 90% success rate, should be first
    assert "cot" in first_strategy_row
    assert "⭐" in first_strategy_row


def test_generate_difficulty_breakdown(temp_md_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that difficulty breakdown tables are generated."""
    content = MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path)

    assert "## Performance by Difficulty" in content
    assert "| Difficulty | Success Rate | Solved | Total |" in content
    assert "easy" in content.lower()
    assert "medium" in content.lower()
    assert "hard" in content.lower()


def test_generate_failed_cases_section(temp_md_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that failed cases section is generated."""
    content = MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path)

    assert "## Failed Cases" in content
    assert "problem_2" in content


def test_generate_limits_failed_cases(temp_md_path: str, sample_metrics: Dict):
    """Test that failed cases are limited to first 10 with overflow message."""
    # Create 15 failed results
    failed_results = []
    for i in range(15):
        result = ExecutionResult(
            problem_id=f"problem_{i}",
            strategy="direct",
            generated_code="def solution(): pass",
            status="failed",
            iterations=[],
            test_results=[],
            error_message="Failed",
            total_tokens=100,
            execution_time_seconds=0.5
        )
        failed_results.append(result)

    results = {"direct": failed_results}

    content = MarkdownGenerator.generate(sample_metrics, results, temp_md_path)

    # Should show first 10 and indicate more
    assert "and 5 more" in content


def test_generate_with_config(temp_md_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that configuration section is included when provided."""
    config = {
        "model": "gpt-4",
        "temperature": 0.7,
        "timeout": 30,
        "max_iterations": 5
    }

    content = MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path, config)

    assert "## Configuration" in content
    assert "**Model:** gpt-4" in content
    assert "**Temperature:** 0.7" in content
    assert "**Timeout:** 30s" in content
    assert "**Max Iterations:** 5" in content


def test_generate_without_config(temp_md_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test generation without configuration section."""
    content = MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path)

    assert "## Configuration" not in content


def test_escape_markdown_special_chars(temp_md_path: str, sample_results: Dict):
    """Test that special Markdown characters are escaped."""
    metrics = {
        "test*strategy": {
            "total_problems": 1,
            "solved_problems": 1,
            "success_rate": 1.0,
            "avg_tokens_per_problem": 100.0,
            "avg_time_per_problem": 1.0,
            "by_difficulty": {}
        }
    }

    content = MarkdownGenerator.generate(metrics, sample_results, temp_md_path)

    # The asterisk should be escaped
    assert "test\\*strategy" in content


def test_generate_creates_parent_directories(tmp_path: Path, sample_metrics: Dict, sample_results: Dict):
    """Test that generate creates parent directories if needed."""
    nested_path = tmp_path / "reports" / "subdir" / "report.md"
    MarkdownGenerator.generate(sample_metrics, sample_results, str(nested_path))

    assert nested_path.exists()
    assert nested_path.parent.exists()


def test_generate_empty_results(temp_md_path: str):
    """Test generation with empty metrics and results."""
    content = MarkdownGenerator.generate({}, {}, temp_md_path)

    # Should still generate valid Markdown with headers
    assert "# LLM Algorithm Harness - Evaluation Report" in content
    assert "## Strategy Performance Summary" in content


def test_generate_redacts_credentials_in_failed_cases(
    temp_md_path: str, sample_metrics: Dict, sample_results: Dict
):
    """Markdown output sanitizes credential text from failed results."""
    secret = "issue4-markdown-export-secret"
    sample_results["direct"][1].error_message = f"Authorization: Bearer {secret}"

    content = MarkdownGenerator.generate(sample_metrics, sample_results, temp_md_path)

    assert secret not in content
    assert "[REDACTED]" in content
