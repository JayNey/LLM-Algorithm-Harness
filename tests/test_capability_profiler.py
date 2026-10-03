"""Unit tests for capability_profiler module."""

import pytest

from src.reporting.capability_profiler import (
    ALL_DIMENSIONS,
    calculate_dimension_scores,
    classify_problem,
    format_dimension_scores_for_radar,
    generate_capability_analysis,
    get_dimension_problem_counts,
    normalize_score_to_100,
)


class TestClassifyProblem:
    """Tests for classify_problem function."""

    def test_single_dimension(self):
        """Test problem with single dimension tag."""
        problem = {"problem_id": "test1", "tags": ["array"]}
        dimensions = classify_problem(problem)
        assert dimensions == ["Array"]

    def test_multiple_dimensions(self):
        """Test problem with multiple dimension tags."""
        problem = {"problem_id": "test2", "tags": ["array", "string"]}
        dimensions = classify_problem(problem)
        assert set(dimensions) == {"Array", "String"}

    def test_no_matching_tags(self):
        """Test problem with no matching dimension tags."""
        problem = {"problem_id": "test3", "tags": ["unknown-tag"]}
        dimensions = classify_problem(problem)
        assert dimensions == []

    def test_empty_tags(self):
        """Test problem with empty tags."""
        problem = {"problem_id": "test4", "tags": []}
        dimensions = classify_problem(problem)
        assert dimensions == []

    def test_tag_normalization(self):
        """Test that tags are normalized correctly."""
        problem = {"problem_id": "test5", "tags": ["GRAPH", "bfs"]}
        dimensions = classify_problem(problem)
        assert "Graph" in dimensions


class TestCalculateDimensionScores:
    """Tests for calculate_dimension_scores function."""

    def test_success_rate_calculation(self):
        """Test success rate calculation for dimensions."""
        problems = [
            {"problem_id": "p1", "tags": ["array"]},
            {"problem_id": "p2", "tags": ["array"]},
        ]
        results = [
            {"problem_id": "p1", "model": "model1", "status": "success"},
            {"problem_id": "p2", "model": "model1", "status": "failed"},
        ]
        scores = calculate_dimension_scores(results, problems)
        assert "model1" in scores
        assert "Array" in scores["model1"]
        assert scores["model1"]["Array"] == pytest.approx(50.0)  # 1/2 = 50%

    def test_dimension_with_no_problems_returns_zero(self):
        """Test that dimension with no problems returns 0.0."""
        problems = [{"problem_id": "p1", "tags": ["array"]}]
        results = [{"problem_id": "p1", "model": "model1", "status": "success"}]
        scores = calculate_dimension_scores(results, problems)
        # Graph dimension should be 0.0 since no problems
        assert scores["model1"]["Graph"] == 0.0

    def test_multiple_models(self):
        """Test scoring with multiple models."""
        problems = [{"problem_id": "p1", "tags": ["array"]}]
        results = [
            {"problem_id": "p1", "model": "model1", "status": "success"},
            {"problem_id": "p1", "model": "model2", "status": "failed"},
        ]
        scores = calculate_dimension_scores(results, problems)
        assert scores["model1"]["Array"] == 100.0
        assert scores["model2"]["Array"] == 0.0


class TestGetDimensionProblemCounts:
    """Tests for get_dimension_problem_counts function."""

    def test_dimension_counts(self):
        """Test counting problems per dimension."""
        problems = [
            {"problem_id": "p1", "tags": ["array"]},
            {"problem_id": "p2", "tags": ["graph"]},
            {"problem_id": "p3", "tags": ["array"]},
        ]
        counts = get_dimension_problem_counts(problems)
        assert counts["Array"] == 2
        assert counts["Graph"] == 1
        assert counts["Dynamic Programming"] == 0

    def test_multi_dimension_problem_not_double_counted(self):
        """Test that multi-dimension problems are counted once per dimension."""
        problems = [{"problem_id": "p1", "tags": ["array", "string"]}]
        counts = get_dimension_problem_counts(problems)
        assert counts["Array"] == 1
        assert counts["String"] == 1


class TestNormalizeScoreTo100:
    """Tests for normalize_score_to_100 function."""

    def test_boundary_values(self):
        """Test boundary value normalization."""
        assert normalize_score_to_100(0.0) == 0.0
        assert normalize_score_to_100(1.0) == 100.0

    def test_middle_values(self):
        """Test middle value normalization."""
        assert normalize_score_to_100(0.5) == 50.0
        assert normalize_score_to_100(0.75) == 75.0
        assert normalize_score_to_100(0.25) == 25.0


class TestGenerateCapabilityAnalysis:
    """Tests for generate_capability_analysis function."""

    def test_identify_strengths_and_weaknesses(self):
        """Test identification of strengths and weaknesses."""
        dimension_scores = {
            "Array": 85.0,  # Strength
            "Graph": 45.0,  # Weakness
            "Dynamic Programming": 60.0,  # Neither
        }
        analysis = generate_capability_analysis(dimension_scores)
        assert "Array" in analysis
        assert "85.0" in analysis
        # Check for strength indicators
        assert "Strength" in analysis or "强项" in analysis

    def test_no_strengths_or_weaknesses(self):
        """Test when there are no clear strengths or weaknesses."""
        dimension_scores = {
            "Array": 60.0,
            "Graph": 65.0,
            "Dynamic Programming": 55.0,
        }
        analysis = generate_capability_analysis(dimension_scores)
        assert "Array" in analysis
        assert "60.0" in analysis

    def test_all_zero_scores(self):
        """Test when all scores are zero."""
        dimension_scores = {dim: 0.0 for dim in ALL_DIMENSIONS}
        analysis = generate_capability_analysis(dimension_scores)
        assert analysis  # Should still generate some analysis


class TestFormatDimensionScoresForRadar:
    """Tests for format_dimension_scores_for_radar function."""

    def test_format_conversion(self):
        """Test conversion from model-first to dimension-first format."""
        model_scores = {
            "model1": {
                "Array": 80.0,
                "Graph": 60.0,
                "Dynamic Programming": 0.0,
                "Greedy": 0.0,
                "Math": 0.0,
                "String": 0.0,
                "Other": 0.0,
            },
            "model2": {
                "Array": 90.0,
                "Graph": 70.0,
                "Dynamic Programming": 0.0,
                "Greedy": 0.0,
                "Math": 0.0,
                "String": 0.0,
                "Other": 0.0,
            },
        }
        formatted = format_dimension_scores_for_radar(model_scores)
        assert "dimension_names" in formatted
        assert "model_scores" in formatted
        # Should include all dimensions
        assert formatted["dimension_names"] == list(ALL_DIMENSIONS)
        # model_scores should map model_name -> list of scores
        assert isinstance(formatted["model_scores"]["model1"], list)
        assert len(formatted["model_scores"]["model1"]) == len(ALL_DIMENSIONS)
        # Check that scores are in the right order
        array_index = list(ALL_DIMENSIONS).index("Array")
        graph_index = list(ALL_DIMENSIONS).index("Graph")
        assert formatted["model_scores"]["model1"][array_index] == 80.0
        assert formatted["model_scores"]["model2"][graph_index] == 70.0

    def test_empty_input(self):
        """Test with empty input."""
        formatted = format_dimension_scores_for_radar({})
        assert formatted["dimension_names"] == []
        assert formatted["model_scores"] == {}
