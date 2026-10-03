"""Integration tests for capability radar chart functionality."""

import pytest

from src.reporting.capability_profiler import (
    calculate_dimension_scores,
    format_dimension_scores_for_radar,
    get_dimension_problem_counts,
)
from src.reporting.chart_generator import ChartGenerator


class TestCapabilityRadarIntegration:
    """Integration tests for the complete capability radar workflow."""

    def test_end_to_end_single_model_workflow(self):
        """Test the complete workflow from raw data to radar chart."""
        # Sample problems with tags
        problems = [
            {"problem_id": "p1", "tags": ["array", "two-pointer"]},
            {"problem_id": "p2", "tags": ["graph", "bfs"]},
            {"problem_id": "p3", "tags": ["array", "sorting"]},
            {"problem_id": "p4", "tags": ["dynamic-programming", "dp"]},
            {"problem_id": "p5", "tags": ["string", "string-matching"]},
        ]

        # Sample execution results
        results = [
            {"problem_id": "p1", "model": "gpt-4", "status": "success"},
            {"problem_id": "p2", "model": "gpt-4", "status": "success"},
            {"problem_id": "p3", "model": "gpt-4", "status": "failed"},
            {"problem_id": "p4", "model": "gpt-4", "status": "success"},
            {"problem_id": "p5", "model": "gpt-4", "status": "failed"},
        ]

        # Step 1: Calculate dimension scores
        dimension_scores = calculate_dimension_scores(results, problems)
        assert "gpt-4" in dimension_scores
        assert "Array" in dimension_scores["gpt-4"]
        assert dimension_scores["gpt-4"]["Array"] == pytest.approx(50.0)  # 1/2
        assert dimension_scores["gpt-4"]["Graph"] == pytest.approx(100.0)  # 1/1
        assert dimension_scores["gpt-4"]["Dynamic Programming"] == pytest.approx(100.0)  # 1/1
        assert dimension_scores["gpt-4"]["String"] == pytest.approx(0.0)  # 0/1

        # Step 2: Get problem counts
        counts = get_dimension_problem_counts(problems)
        assert counts["Array"] == 2
        assert counts["Graph"] == 1
        assert counts["Dynamic Programming"] == 1
        assert counts["String"] == 1

        # Step 3: Format for radar chart
        formatted = format_dimension_scores_for_radar(dimension_scores)
        assert "dimension_names" in formatted
        assert "model_scores" in formatted
        assert len(formatted["model_scores"]["gpt-4"]) == len(formatted["dimension_names"])

        # Step 4: Generate radar chart
        chart_gen = ChartGenerator()
        radar_chart = chart_gen.generate_capability_radar(
            dimension_scores, ["gpt-4"], formatted["dimension_names"]
        )
        assert isinstance(radar_chart, str)
        assert len(radar_chart) > 0

    def test_end_to_end_multi_model_workflow(self):
        """Test the complete workflow with multiple models."""
        # Sample problems
        problems = [
            {"problem_id": "p1", "tags": ["array"]},
            {"problem_id": "p2", "tags": ["graph"]},
            {"problem_id": "p3", "tags": ["dp"]},
        ]

        # Results for multiple models
        results = [
            {"problem_id": "p1", "model": "gpt-4", "status": "success"},
            {"problem_id": "p2", "model": "gpt-4", "status": "success"},
            {"problem_id": "p3", "model": "gpt-4", "status": "failed"},
            {"problem_id": "p1", "model": "claude-3", "status": "success"},
            {"problem_id": "p2", "model": "claude-3", "status": "failed"},
            {"problem_id": "p3", "model": "claude-3", "status": "success"},
        ]

        # Calculate scores
        dimension_scores = calculate_dimension_scores(results, problems)
        assert "gpt-4" in dimension_scores
        assert "claude-3" in dimension_scores

        # Format and generate
        formatted = format_dimension_scores_for_radar(dimension_scores)
        chart_gen = ChartGenerator()
        radar_chart = chart_gen.generate_capability_radar(
            dimension_scores, ["gpt-4", "claude-3"], formatted["dimension_names"]
        )
        assert isinstance(radar_chart, str)
        assert len(radar_chart) > 0

    def test_html_report_with_capability_radar(self):
        """Test generating an HTML report with capability radar chart."""
        # Sample data
        problems = [
            {"problem_id": "p1", "title": "Two Sum", "tags": ["array"], "difficulty": "easy"},
            {"problem_id": "p2", "title": "BFS", "tags": ["graph", "bfs"], "difficulty": "medium"},
        ]

        results = [
            {
                "problem_id": "p1",
                "model": "test-model",
                "status": "success",
                "execution_time": 1.0,
                "generated_code": "code",
            },
            {
                "problem_id": "p2",
                "model": "test-model",
                "status": "failed",
                "execution_time": 2.0,
                "generated_code": "code",
            },
        ]

        # Calculate dimension data
        dimension_scores = calculate_dimension_scores(results, problems)
        counts = get_dimension_problem_counts(problems)

        # Verify dimension data is computed
        assert "test-model" in dimension_scores
        assert counts["Array"] == 1
        assert counts["Graph"] == 1

        # Generate chart
        formatted = format_dimension_scores_for_radar(dimension_scores)
        chart_gen = ChartGenerator()
        radar_chart = chart_gen.generate_capability_radar(
            dimension_scores, ["test-model"], formatted["dimension_names"]
        )

        # Verify chart is valid base64 string
        assert isinstance(radar_chart, str)
        assert len(radar_chart) > 0

        # Note: Full HTML generation would require more mock data,
        # but this verifies the key integration points work

    def test_empty_data_graceful_handling(self):
        """Test that empty data is handled gracefully."""
        problems = []
        results = []

        # Should not crash
        dimension_scores = calculate_dimension_scores(results, problems)
        counts = get_dimension_problem_counts(problems)

        assert dimension_scores == {}
        assert all(count == 0 for count in counts.values())

        # Empty scores should still format
        formatted = format_dimension_scores_for_radar(dimension_scores)
        assert formatted["dimension_names"] == []
        assert formatted["model_scores"] == {}

    def test_real_world_scenario_with_varied_performance(self):
        """Test a realistic scenario with varied model performance across dimensions."""
        # Simulate a realistic problem set
        problems = [
            {"problem_id": "arr1", "tags": ["array", "two-pointer"]},
            {"problem_id": "arr2", "tags": ["array", "sorting"]},
            {"problem_id": "arr3", "tags": ["array", "hash-table"]},
            {"problem_id": "graph1", "tags": ["graph", "bfs"]},
            {"problem_id": "graph2", "tags": ["graph", "dfs"]},
            {"problem_id": "dp1", "tags": ["dp", "memoization"]},
            {"problem_id": "dp2", "tags": ["dynamic-programming"]},
            {"problem_id": "dp3", "tags": ["dp"]},
            {"problem_id": "greedy1", "tags": ["greedy", "interval"]},
            {"problem_id": "string1", "tags": ["string", "string-matching"]},
            {"problem_id": "math1", "tags": ["math", "number-theory"]},
        ]

        # Model with strong array/graph, weak DP
        results = [
            # Array: 3/3 = 100%
            {"problem_id": "arr1", "model": "model-a", "status": "success"},
            {"problem_id": "arr2", "model": "model-a", "status": "success"},
            {"problem_id": "arr3", "model": "model-a", "status": "success"},
            # Graph: 1/2 = 50%
            {"problem_id": "graph1", "model": "model-a", "status": "success"},
            {"problem_id": "graph2", "model": "model-a", "status": "failed"},
            # DP: 0/3 = 0%
            {"problem_id": "dp1", "model": "model-a", "status": "failed"},
            {"problem_id": "dp2", "model": "model-a", "status": "failed"},
            {"problem_id": "dp3", "model": "model-a", "status": "failed"},
            # Greedy: 1/1 = 100%
            {"problem_id": "greedy1", "model": "model-a", "status": "success"},
            # String: 0/1 = 0%
            {"problem_id": "string1", "model": "model-a", "status": "failed"},
            # Math: 1/1 = 100%
            {"problem_id": "math1", "model": "model-a", "status": "success"},
        ]

        dimension_scores = calculate_dimension_scores(results, problems)

        # Verify expected scores
        assert dimension_scores["model-a"]["Array"] == pytest.approx(100.0)
        assert dimension_scores["model-a"]["Graph"] == pytest.approx(50.0)
        assert dimension_scores["model-a"]["Dynamic Programming"] == pytest.approx(0.0)
        assert dimension_scores["model-a"]["Greedy"] == pytest.approx(100.0)
        assert dimension_scores["model-a"]["String"] == pytest.approx(0.0)
        assert dimension_scores["model-a"]["Math"] == pytest.approx(100.0)

        # Generate radar chart
        formatted = format_dimension_scores_for_radar(dimension_scores)
        chart_gen = ChartGenerator()
        radar_chart = chart_gen.generate_capability_radar(
            dimension_scores, ["model-a"], formatted["dimension_names"]
        )

        assert isinstance(radar_chart, str)
        assert len(radar_chart) > 100  # Should be substantial base64 string
