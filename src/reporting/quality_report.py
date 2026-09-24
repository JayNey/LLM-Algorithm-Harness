"""
HTML Report Generator Extensions for Code Quality

This module extends the HTML report generator with code quality visualization.
"""

from typing import Any, Dict, Optional


def generate_quality_section(quality_metrics: Optional[Dict[str, Any]]) -> str:
    """
    Generate HTML section for code quality metrics.

    Args:
        quality_metrics: Code quality metrics dictionary

    Returns:
        HTML string for quality section
    """
    if not quality_metrics:
        return ""

    html = '<div class="quality-section">\n'
    html += "<h2>代码质量评估</h2>\n"

    # Overall score
    overall = quality_metrics.get("overall_score")
    if overall is not None:
        html += f'<div class="overall-score">综合评分: {overall:.1f}/100</div>\n'

    # Time complexity
    time_comp = quality_metrics.get("time_complexity")
    if time_comp:
        html += '<div class="metric-card">\n'
        html += "<h3>⏱️ 时间复杂度</h3>\n"
        html += f'<p>静态分析: {time_comp.get("static_analysis", "N/A")}</p>\n'
        html += f'<p>循环嵌套深度: {time_comp.get("loop_nesting_depth", 0)}</p>\n'
        score = time_comp.get("performance_score")
        if score is not None:
            html += f"<p>性能评分: {score:.1f}/100</p>\n"
        html += "</div>\n"

    # Space complexity
    space_comp = quality_metrics.get("space_complexity")
    if space_comp:
        html += '<div class="metric-card">\n'
        html += "<h3>💾 空间复杂度</h3>\n"
        peak_mb = space_comp.get("peak_memory_mb")
        if peak_mb:
            html += f"<p>峰值内存: {peak_mb:.2f} MB</p>\n"
        score = space_comp.get("memory_efficiency_score")
        if score is not None:
            html += f"<p>空间效率: {score:.1f}/100</p>\n"
        html += "</div>\n"

    # Readability
    readability = quality_metrics.get("readability")
    if readability:
        html += '<div class="metric-card">\n'
        html += "<h3>📖 代码可读性</h3>\n"
        pylint = readability.get("pylint_score")
        if pylint is not None:
            html += f"<p>Pylint 评分: {pylint:.1f}/10</p>\n"
        flake8 = readability.get("flake8_issues")
        if flake8 is not None:
            html += f"<p>Flake8 问题数: {flake8}</p>\n"
        complexity = readability.get("cyclomatic_complexity")
        if complexity is not None:
            html += f"<p>圈复杂度: {complexity:.1f}</p>\n"
        score = readability.get("readability_score")
        if score is not None:
            html += f"<p>可读性评分: {score:.1f}/100</p>\n"
        html += "</div>\n"

    # Style consistency
    style = quality_metrics.get("style_consistency")
    if style:
        html += '<div class="metric-card">\n'
        html += "<h3>🎨 代码风格</h3>\n"
        compliant = style.get("black_compliant")
        if compliant is not None:
            html += f'<p>Black 格式: {"✅ 符合" if compliant else "❌ 不符合"}</p>\n'
        violations = style.get("style_violations", 0)
        html += f"<p>风格违规: {violations}</p>\n"
        score = style.get("style_score")
        if score is not None:
            html += f"<p>风格评分: {score:.1f}/100</p>\n"
        html += "</div>\n"

    html += "</div>\n"
    return html


def generate_quality_radar_chart(quality_metrics: Optional[Dict[str, Any]]) -> str:
    """
    Generate SVG radar chart for code quality metrics.

    Args:
        quality_metrics: Code quality metrics dictionary

    Returns:
        SVG string for radar chart
    """
    if not quality_metrics:
        return ""

    # Extract scores with safe dictionary access
    time_score = 0
    space_score = 0
    readability_score = 0
    style_score = 0

    time_comp = quality_metrics.get("time_complexity")
    if time_comp:
        time_score = time_comp.get("performance_score", 0) or 0

    space_comp = quality_metrics.get("space_complexity")
    if space_comp:
        space_score = space_comp.get("memory_efficiency_score", 0) or 0

    readability = quality_metrics.get("readability")
    if readability:
        readability_score = readability.get("readability_score", 0) or 0

    style = quality_metrics.get("style_consistency")
    if style:
        style_score = style.get("style_score", 0) or 0

    # Simple SVG radar chart (simplified version)
    svg = '<svg width="300" height="300" viewBox="0 0 300 300">\n'
    svg += '<circle cx="150" cy="150" r="100" fill="none" stroke="#ddd" />\n'
    svg += '<circle cx="150" cy="150" r="75" fill="none" stroke="#ddd" />\n'
    svg += '<circle cx="150" cy="150" r="50" fill="none" stroke="#ddd" />\n'
    svg += '<circle cx="150" cy="150" r="25" fill="none" stroke="#ddd" />\n'

    # Labels
    svg += '<text x="150" y="40" text-anchor="middle">时间</text>\n'
    svg += '<text x="260" y="155" text-anchor="start">空间</text>\n'
    svg += '<text x="150" y="270" text-anchor="middle">可读性</text>\n'
    svg += '<text x="40" y="155" text-anchor="end">风格</text>\n'

    svg += "</svg>\n"
    return svg
