"""
HTML report generation module.
"""

import base64
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.models import ExecutionResult
from src.reporting.chart_generator import ChartGenerator
from src.utils.secrets import redact_sensitive_text

logger = logging.getLogger(__name__)


class HTMLGenerator:
    """Generate self-contained HTML evaluation reports."""

    @staticmethod
    def _get_embedded_css() -> str:
        """Return embedded CSS styles."""
        return """
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                line-height: 1.6;
                color: #333;
                background-color: #f5f5f5;
                padding: 20px;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }

            h1 {
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }

            h2 {
                color: #34495e;
                margin-top: 30px;
                margin-bottom: 15px;
                border-left: 4px solid #3498db;
                padding-left: 10px;
            }

            .metadata {
                background-color: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }

            .metadata p {
                margin: 5px 0;
            }

            .card {
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 20px;
                margin: 15px 0;
                background-color: #fff;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }

            .card-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }

            .card-title {
                font-size: 1.3em;
                font-weight: bold;
                color: #2c3e50;
            }

            .badge {
                padding: 5px 12px;
                border-radius: 999px;
                font-size: 0.85em;
                font-weight: bold;
            }

            .badge-success {
                background-color: #2ecc71;
                color: white;
            }

            .badge-warning {
                background-color: #f39c12;
                color: white;
            }

            .badge-danger {
                background-color: #e74c3c;
                color: white;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
            }

            table th, table td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }

            table th {
                background-color: #3498db;
                color: white;
                cursor: pointer;
                user-select: none;
            }

            table th:hover {
                background-color: #2980b9;
            }

            table tr:hover {
                background-color: #f8f9fa;
            }

            .chart-container {
                text-align: center;
                margin: 20px 0;
            }

            .chart-container img {
                max-width: 100%;
                height: auto;
                border-radius: 5px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }

            .details-toggle {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.9em;
            }

            .details-toggle:hover {
                background-color: #2980b9;
            }

            .details-content {
                display: none;
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #ddd;
            }

            .footer {
                margin-top: 40px;
                padding-top: 20px;
                border-top: 1px solid #ddd;
                text-align: center;
                color: #7f8c8d;
                font-size: 0.9em;
            }

            @media (max-width: 768px) {
                body {
                    padding: 10px;
                }

                .container {
                    padding: 15px;
                }

                table {
                    font-size: 0.9em;
                }
            }

            .error-container {
                background-color: #fff5f5;
                border: 1px solid #fc8181;
                border-left: 4px solid #f56565;
                border-radius: 5px;
                padding: 15px;
                margin: 15px 0;
            }

            .error-title {
                color: #c53030;
                font-weight: bold;
                margin-bottom: 8px;
                display: flex;
                align-items: center;
            }

            .error-icon {
                margin-right: 8px;
                font-size: 1.2em;
            }

            .error-message {
                color: #742a2a;
                margin: 5px 0;
                font-family: monospace;
                font-size: 0.9em;
            }

            .error-details {
                margin-top: 10px;
                padding-top: 10px;
                border-top: 1px solid #fc8181;
                font-size: 0.85em;
                color: #742a2a;
            }

            .error-toggle {
                background-color: #fc8181;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                cursor: pointer;
                font-size: 0.85em;
                margin-top: 8px;
            }

            .error-toggle:hover {
                background-color: #f56565;
            }

            .chart-placeholder {
                background-color: #f7fafc;
                border: 2px dashed #cbd5e0;
                border-radius: 5px;
                padding: 40px;
                text-align: center;
                color: #718096;
                margin: 20px 0;
            }

            .chart-placeholder-icon {
                font-size: 3em;
                margin-bottom: 10px;
                opacity: 0.5;
            }
        </style>
        """

    @staticmethod
    def _get_embedded_js() -> str:
        """Return embedded JavaScript for table sorting."""
        return """
        <script>
        function toggleDetails(id) {
            const element = document.getElementById(id);
            if (element.style.display === 'none' || element.style.display === '') {
                element.style.display = 'block';
            } else {
                element.style.display = 'none';
            }
        }

        function sortTable(tableId, columnIndex) {
            const table = document.getElementById(tableId);
            const rows = Array.from(table.querySelectorAll('tbody tr'));
            const isNumeric = !isNaN(parseFloat(rows[0].cells[columnIndex].textContent));

            rows.sort((a, b) => {
                const aValue = a.cells[columnIndex].textContent;
                const bValue = b.cells[columnIndex].textContent;

                if (isNumeric) {
                    return parseFloat(aValue) - parseFloat(bValue);
                } else {
                    return aValue.localeCompare(bValue);
                }
            });

            const tbody = table.querySelector('tbody');
            rows.forEach(row => tbody.appendChild(row));
        }
        </script>
        """

    @staticmethod
    def _format_chart_error(chart_name: str, error: Exception, show_traceback: bool = False) -> str:
        """
        Format a chart generation error as HTML.

        Args:
            chart_name: Name of the chart that failed
            error: The exception that was raised
            show_traceback: Whether to include full traceback

        Returns:
            Formatted HTML error message
        """
        error_id = f"error-details-{chart_name.replace(' ', '-').lower()}"
        error_type = type(error).__name__
        error_msg = str(error)

        html_parts = []
        html_parts.append("<div class='error-container'>")
        html_parts.append("<div class='error-title'>")
        html_parts.append("<span class='error-icon'>⚠️</span>")
        html_parts.append(f"<span>Failed to generate {chart_name}</span>")
        html_parts.append("</div>")
        html_parts.append(f"<div class='error-message'><strong>{error_type}:</strong> {error_msg}</div>")

        if show_traceback:
            tb_str = traceback.format_exc()
            html_parts.append(f"<button class='error-toggle' onclick='toggleDetails(\"{error_id}\")'>Show Technical Details</button>")
            html_parts.append(f"<div id='{error_id}' class='error-details' style='display: none;'>")
            html_parts.append("<pre style='white-space: pre-wrap; word-wrap: break-word;'>")
            html_parts.append(tb_str)
            html_parts.append("</pre>")
            html_parts.append("</div>")

        html_parts.append("</div>")

        # Add placeholder
        html_parts.append("<div class='chart-placeholder'>")
        html_parts.append("<div class='chart-placeholder-icon'>📊</div>")
        html_parts.append(f"<p>{chart_name} could not be rendered</p>")
        html_parts.append("</div>")

        return "\n".join(html_parts)

    @staticmethod
    def generate(
        metrics: Dict[str, Dict],
        results: Dict[str, List[ExecutionResult]],
        output_path: str,
        include_charts: bool = True,
        config: Dict = None
    ) -> str:
        """
        Generate self-contained HTML report.

        Args:
            metrics: Dictionary mapping strategy name to metrics dict
            results: Dictionary mapping strategy name to results list
            output_path: Path to save the HTML file
            include_charts: Whether to include embedded charts
            config: Optional evaluation configuration dict

        Returns:
            Generated HTML content
        """
        html_parts = []

        # HTML header
        html_parts.append("<!DOCTYPE html>")
        html_parts.append("<html lang='en'>")
        html_parts.append("<head>")
        html_parts.append("<meta charset='UTF-8'>")
        html_parts.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
        html_parts.append("<title>LLM Algorithm Harness - Evaluation Report</title>")
        html_parts.append(HTMLGenerator._get_embedded_css())
        html_parts.append("</head>")
        html_parts.append("<body>")
        html_parts.append("<div class='container'>")

        # Title
        html_parts.append("<h1>LLM Algorithm Harness - Evaluation Report</h1>")

        # Metadata
        html_parts.append("<div class='metadata'>")
        html_parts.append(f"<p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>")
        if config:
            html_parts.append(f"<p><strong>Model:</strong> {config.get('model', 'N/A')}</p>")
            html_parts.append(f"<p><strong>Temperature:</strong> {config.get('temperature', 'N/A')}</p>")
            html_parts.append(f"<p><strong>Timeout:</strong> {config.get('timeout', 'N/A')}s</p>")
        html_parts.append("</div>")

        # Strategy Summary Cards
        html_parts.append("<h2>Strategy Overview</h2>")

        sorted_strategies = sorted(
            metrics.items(),
            key=lambda x: x[1].get('success_rate', 0),
            reverse=True
        )

        for idx, (strategy_name, strategy_metrics) in enumerate(sorted_strategies):
            success_rate = strategy_metrics.get('success_rate', 0) * 100
            solved = strategy_metrics.get('solved_problems', 0)
            total = strategy_metrics.get('total_problems', 0)
            avg_tokens = strategy_metrics.get('avg_tokens_per_problem', 0)

            # Badge color based on success rate
            if success_rate >= 80:
                badge_class = 'badge-success'
            elif success_rate >= 50:
                badge_class = 'badge-warning'
            else:
                badge_class = 'badge-danger'

            html_parts.append("<div class='card'>")
            html_parts.append("<div class='card-header'>")
            html_parts.append(f"<span class='card-title'>{strategy_name}</span>")
            html_parts.append(f"<span class='badge {badge_class}'>{success_rate:.1f}% Success</span>")
            html_parts.append("</div>")
            html_parts.append(f"<p><strong>Solved:</strong> {solved}/{total} problems</p>")
            html_parts.append(f"<p><strong>Avg Tokens:</strong> {avg_tokens:.0f}</p>")

            # Details toggle
            details_id = f"details-{idx}"
            html_parts.append(f"<button class='details-toggle' onclick='toggleDetails(\"{details_id}\")'>Show Details</button>")
            html_parts.append(f"<div id='{details_id}' class='details-content'>")

            # Difficulty breakdown
            by_difficulty = strategy_metrics.get('by_difficulty', {})
            if by_difficulty:
                html_parts.append("<h3>By Difficulty</h3>")
                html_parts.append("<table>")
                html_parts.append("<tr><th>Difficulty</th><th>Success Rate</th><th>Solved</th></tr>")
                for diff in ['easy', 'medium', 'hard']:
                    if diff in by_difficulty:
                        diff_data = by_difficulty[diff]
                        rate = diff_data.get('success_rate', 0) * 100
                        solved_diff = diff_data.get('solved', 0)
                        total_diff = diff_data.get('total', 0)
                        html_parts.append(f"<tr><td>{diff.capitalize()}</td><td>{rate:.1f}%</td><td>{solved_diff}/{total_diff}</td></tr>")
                html_parts.append("</table>")

            html_parts.append("</div>")  # details-content
            html_parts.append("</div>")  # card

        # Charts
        if include_charts:
            html_parts.append("<h2>Performance Charts</h2>")

            # Success rate chart
            chart_buf = ChartGenerator.generate_success_rate_chart(metrics)
            if chart_buf:
                try:
                    chart_b64 = base64.b64encode(chart_buf.read()).decode('utf-8')
                    html_parts.append("<div class='chart-container'>")
                    html_parts.append("<h3>Success Rate Comparison</h3>")
                    html_parts.append(f"<img src='data:image/png;base64,{chart_b64}' alt='Success Rate Chart'>")
                    html_parts.append("</div>")
                except Exception as e:
                    logger.error(f"Failed to encode success rate chart: {str(e)}", exc_info=True)
                    html_parts.append(HTMLGenerator._format_chart_error("Success Rate Chart", e, show_traceback=True))
            else:
                logger.error("Success rate chart generation returned None")
                error = Exception("Chart generation failed")
                html_parts.append(HTMLGenerator._format_chart_error("Success Rate Chart", error, show_traceback=False))

            # Token chart with cost estimation
            model_name = config.get('model') if config else None
            token_buf = ChartGenerator.generate_token_chart(metrics, results, model_name)
            if token_buf:
                try:
                    token_b64 = base64.b64encode(token_buf.read()).decode('utf-8')
                    html_parts.append("<div class='chart-container'>")
                    html_parts.append("<h3>Token Consumption and Cost</h3>")
                    html_parts.append(f"<img src='data:image/png;base64,{token_b64}' alt='Token Chart'>")
                    html_parts.append("</div>")
                except Exception as e:
                    logger.error(f"Failed to encode token chart: {str(e)}", exc_info=True)
                    html_parts.append(HTMLGenerator._format_chart_error("Token Chart", e, show_traceback=True))
            else:
                logger.error("Token chart generation returned None")
                error = Exception("Chart generation failed")
                html_parts.append(HTMLGenerator._format_chart_error("Token Chart", error, show_traceback=False))

            # Iteration distribution
            iter_buf = ChartGenerator.generate_iteration_distribution(results)
            if iter_buf:
                try:
                    iter_b64 = base64.b64encode(iter_buf.read()).decode('utf-8')
                    html_parts.append("<div class='chart-container'>")
                    html_parts.append("<h3>Iteration Distribution</h3>")
                    html_parts.append(f"<img src='data:image/png;base64,{iter_b64}' alt='Iteration Distribution'>")
                    html_parts.append("</div>")
                except Exception as e:
                    logger.error(f"Failed to encode iteration distribution: {str(e)}", exc_info=True)
                    html_parts.append(HTMLGenerator._format_chart_error("Iteration Distribution Chart", e, show_traceback=True))
            else:
                logger.info("Iteration distribution chart returned None (no multi-round data)")
                html_parts.append("<div class='chart-placeholder'>")
                html_parts.append("<div class='chart-placeholder-icon'>📊</div>")
                html_parts.append("<p>Iteration Distribution chart: No multi-round data available</p>")
                html_parts.append("</div>")


        # Footer
        html_parts.append("<div class='footer'>")
        html_parts.append("<p>Generated by LLM Algorithm Harness</p>")
        html_parts.append("</div>")

        html_parts.append("</div>")  # container
        html_parts.append(HTMLGenerator._get_embedded_js())
        html_parts.append("</body>")
        html_parts.append("</html>")

        html_content = redact_sensitive_text("\n".join(html_parts))

        # Save to file
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        output_path_obj.write_text(html_content, encoding='utf-8')

        return html_content
