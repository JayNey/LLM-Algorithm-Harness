"""Tests for the code quality HTML report section."""

from src.reporting.quality_report import generate_quality_section


def test_empty_metrics_render_nothing():
    assert generate_quality_section(None) == ""
    assert generate_quality_section({}) == ""


def test_full_metrics_render_all_sections():
    metrics = {
        "overall_score": 87.5,
        "time_complexity": {
            "static_analysis": "O(n log n)",
            "loop_nesting_depth": 2,
            "performance_score": 90.0,
        },
        "space_complexity": {"peak_memory_mb": 12.345, "memory_efficiency_score": 80.0},
        "readability": {
            "pylint_score": 8.9,
            "flake8_issues": 3,
            "cyclomatic_complexity": 4.5,
            "readability_score": 77.0,
        },
        "style_consistency": {
            "black_compliant": True,
            "style_violations": 1,
            "style_score": 95.0,
        },
    }
    html = generate_quality_section(metrics)

    assert "代码质量评估" in html
    assert "综合评分: 87.5/100" in html
    assert "O(n log n)" in html
    assert "循环嵌套深度: 2" in html
    assert "性能评分: 90.0/100" in html
    assert "峰值内存: 12.35 MB" in html
    assert "空间效率: 80.0/100" in html
    assert "Pylint 评分: 8.9/10" in html
    assert "Flake8 问题数: 3" in html
    assert "圈复杂度: 4.5" in html
    assert "可读性评分: 77.0/100" in html
    assert "✅ 符合" in html
    assert "风格违规: 1" in html
    assert "风格评分: 95.0/100" in html


def test_partial_metrics_render_only_present_parts():
    html = generate_quality_section(
        {"overall_score": 50.0, "time_complexity": {"static_analysis": "O(1)"}}
    )
    assert "综合评分: 50.0/100" in html
    assert "静态分析: O(1)" in html
    assert "性能评分" not in html
    assert "空间复杂度" not in html
    assert "代码可读性" not in html
    assert "代码风格" not in html


def test_black_non_compliant_marked():
    html = generate_quality_section(
        {"style_consistency": {"black_compliant": False, "style_violations": 7}}
    )
    assert "❌ 不符合" in html
    assert "风格违规: 7" in html


def test_radar_chart_empty_metrics():
    from src.reporting.quality_report import generate_quality_radar_chart

    assert generate_quality_radar_chart(None) == ""


def test_radar_chart_renders_labels_and_defaults():
    from src.reporting.quality_report import generate_quality_radar_chart

    svg = generate_quality_radar_chart({"time_complexity": {}})
    assert svg.startswith("<svg")
    assert "时间" in svg and "空间" in svg and "可读性" in svg and "风格" in svg
    assert svg.endswith("</svg>\n")


def test_radar_chart_uses_scores_when_present():
    from src.reporting.quality_report import generate_quality_radar_chart

    svg = generate_quality_radar_chart(
        {
            "time_complexity": {"performance_score": 88.0},
            "space_complexity": {"memory_efficiency_score": None},
            "readability": {"readability_score": 60.0},
            "style_consistency": {"style_score": 0},
        }
    )
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>\n")


def test_radar_chart_none_scores_fall_back_to_zero():
    from src.reporting.quality_report import generate_quality_radar_chart

    metrics = {"time_complexity": {"performance_score": None}}
    svg = generate_quality_radar_chart(metrics)
    assert svg.startswith("<svg")
