"""
Unit tests for HTMLGenerator.
"""

from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.models import ExecutionResult, TestCaseResult
from src.reporting.html_generator import HTMLGenerator


@pytest.fixture
def temp_html_path(tmp_path: Path) -> str:
    """Fixture for temporary HTML file path."""
    return str(tmp_path / "test_report.html")


@pytest.fixture
def sample_metrics() -> Dict[str, Dict]:
    """Fixture for sample strategy metrics."""
    return {
        "direct": {
            "total_problems": 10,
            "solved_problems": 8,
            "success_rate": 0.8,
            "avg_tokens_per_problem": 500.0,
            "by_difficulty": {
                "easy": {"total": 5, "solved": 5, "success_rate": 1.0},
                "medium": {"total": 3, "solved": 2, "success_rate": 0.67},
                "hard": {"total": 2, "solved": 1, "success_rate": 0.5}
            }
        },
        "cot": {
            "total_problems": 10,
            "solved_problems": 5,
            "success_rate": 0.5,
            "avg_tokens_per_problem": 800.0,
            "by_difficulty": {}
        }
    }


@pytest.fixture
def sample_results() -> Dict[str, List[ExecutionResult]]:
    """Fixture for sample execution results."""
    result = ExecutionResult(
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

    return {"direct": [result], "cot": [result]}


def test_generate_creates_html_file(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that generate creates an HTML file."""
    HTMLGenerator.generate(sample_metrics, sample_results, temp_html_path)

    assert Path(temp_html_path).exists()


def test_generate_valid_html5_structure(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that generated HTML has valid HTML5 structure."""
    content = HTMLGenerator.generate(sample_metrics, sample_results, temp_html_path)

    assert content.startswith("<!DOCTYPE html>")
    assert "<html lang='en'>" in content
    assert "<head>" in content
    assert "<meta charset='UTF-8'>" in content
    assert "<meta name='viewport'" in content
    assert "<title>" in content
    assert "</html>" in content


def test_generate_contains_embedded_css(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that HTML contains embedded CSS with no external dependencies."""
    content = HTMLGenerator.generate(sample_metrics, sample_results, temp_html_path)

    assert "<style>" in content
    assert "</style>" in content
    # Check for some key CSS rules
    assert "font-family:" in content
    assert ".container" in content
    assert ".card" in content
    assert "table" in content


def test_generate_contains_embedded_js(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that HTML contains embedded JavaScript."""
    content = HTMLGenerator.generate(sample_metrics, sample_results, temp_html_path)

    assert "<script>" in content
    assert "</script>" in content
    assert "function toggleDetails" in content
    assert "function sortTable" in content


def test_generate_includes_metadata(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that HTML includes metadata section."""
    config = {
        "model": "gpt-4",
        "temperature": 0.7,
        "timeout": 30
    }

    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=False,
        config=config
    )

    assert "Generated:" in content
    assert "Model:</strong> gpt-4" in content
    assert "Temperature:</strong> 0.7" in content
    assert "Timeout:</strong> 30s" in content


def test_generate_strategy_cards(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that strategy cards are generated."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=False
    )

    assert "Strategy Overview" in content
    assert "direct" in content
    assert "cot" in content
    assert "80.0% Success" in content
    assert "50.0% Success" in content


def test_generate_badge_color_coding(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that badges are color-coded based on success rate."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=False
    )

    # 80% should get badge-success
    assert "badge-success" in content
    # 50% should get badge-warning
    assert "badge-warning" in content


def test_generate_collapsible_details(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that collapsible detail sections are created."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=False
    )

    assert "details-toggle" in content
    assert "toggleDetails" in content
    assert "details-content" in content
    assert "Show Details" in content


def test_generate_with_charts(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that charts are embedded as base64 when include_charts=True."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=True
    )

    # Should contain base64 encoded images
    assert "data:image/png;base64," in content
    assert "Performance Charts" in content


def test_generate_without_charts(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test generation without charts."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=False
    )

    # Should not contain chart data
    assert "data:image/png;base64," not in content


def test_generate_responsive_design(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that HTML includes responsive design CSS."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=False
    )

    # Check for media queries
    assert "@media" in content
    assert "max-width" in content


def test_generate_redacts_credentials_from_rendering_errors(
    temp_html_path: str, sample_metrics: Dict, sample_results: Dict
):
    """HTML output sanitizes exceptions raised while rendering charts."""
    secret = "issue4-html-export-secret"
    chart_buffer = MagicMock()
    chart_buffer.read.side_effect = Exception(f"chart failed with api_key={secret}")
    with patch(
        "src.reporting.html_generator.ChartGenerator.generate_success_rate_chart",
        return_value=chart_buffer,
    ):
        content = HTMLGenerator.generate(
            sample_metrics,
            sample_results,
            temp_html_path,
            include_charts=True,
        )

    assert secret not in content
    assert "[REDACTED]" in content


def test_generate_footer(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that footer is included."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=False
    )

    assert "footer" in content
    assert "Generated by LLM Algorithm Harness" in content


def test_generate_creates_parent_directories(tmp_path: Path, sample_metrics: Dict, sample_results: Dict):
    """Test that generate creates parent directories if needed."""
    nested_path = tmp_path / "reports" / "subdir" / "report.html"

    HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        str(nested_path),
        include_charts=False
    )

    assert nested_path.exists()
    assert nested_path.parent.exists()


def test_generate_difficulty_breakdown_in_details(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that difficulty breakdown appears in detail sections."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=False
    )

    assert "By Difficulty" in content
    # Check for difficulty levels in the direct strategy details
    assert "easy" in content.lower()
    assert "medium" in content.lower()
    assert "hard" in content.lower()


def test_generate_empty_metrics(temp_html_path: str):
    """Test generation with empty metrics and results."""
    content = HTMLGenerator.generate({}, {}, temp_html_path, include_charts=False)

    # Should still generate valid HTML
    assert "<!DOCTYPE html>" in content
    assert "LLM Algorithm Harness" in content


def test_generate_self_contained(temp_html_path: str, sample_metrics: Dict, sample_results: Dict):
    """Test that generated HTML is self-contained (no external resources)."""
    content = HTMLGenerator.generate(
        sample_metrics,
        sample_results,
        temp_html_path,
        include_charts=True
    )

    # Should not reference external CSS/JS/images
    assert 'href="http' not in content
    assert 'src="http' not in content
    assert '<link' not in content  # No external stylesheets


def test_html_strategy_card_shows_failure_counts(temp_html_path: str):
    """Strategy cards report model and system failure counts."""
    def _result(pid: str, status: str, category) -> ExecutionResult:
        return ExecutionResult(
            problem_id=pid,
            strategy="direct",
            generated_code="",
            status=status,
            failure_category=category,
            iterations=[],
            test_results=[],
            total_tokens=10,
        )

    results = {
        "direct": [
            _result("p1", "success", None),
            _result("p2", "error", "model_error"),
            _result("p3", "error", "system_error"),
        ]
    }
    metrics = {
        "direct": {
            "total_problems": 3,
            "solved_problems": 1,
            "success_rate": 1 / 3,
            "avg_tokens_per_problem": 10.0,
        }
    }

    HTMLGenerator.generate(metrics, results, temp_html_path, include_charts=False)

    content = Path(temp_html_path).read_text()
    assert "<strong>Model failed:</strong> 1" in content
    assert "<strong>System failed:</strong> 1" in content
