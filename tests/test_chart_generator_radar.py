"""Unit tests for ChartGenerator.generate_capability_radar method."""

import base64
import io

from PIL import Image

from src.reporting.capability_profiler import ALL_DIMENSIONS
from src.reporting.chart_generator import ChartGenerator


class TestGenerateCapabilityRadar:
    """Tests for generate_capability_radar method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.chart_gen = ChartGenerator()

    def test_single_model_radar_chart(self):
        """Test radar chart generation for a single model."""
        dimension_scores = {"model1": {dim: 50.0 for dim in ALL_DIMENSIONS}}
        model_names = ["model1"]
        dimension_names = list(ALL_DIMENSIONS)

        result = self.chart_gen.generate_capability_radar(
            dimension_scores, model_names, dimension_names
        )

        # Verify it returns a base64 string
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify it's valid base64 that decodes to a valid PNG
        img_data = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_data))
        assert img.format == "PNG"
        assert img.size[0] > 0 and img.size[1] > 0

    def test_multiple_models_radar_chart(self):
        """Test radar chart generation for multiple models."""
        dimension_scores = {
            "model1": {dim: 60.0 for dim in ALL_DIMENSIONS},
            "model2": {dim: 80.0 for dim in ALL_DIMENSIONS},
            "model3": {dim: 40.0 for dim in ALL_DIMENSIONS},
        }
        model_names = ["model1", "model2", "model3"]
        dimension_names = list(ALL_DIMENSIONS)

        result = self.chart_gen.generate_capability_radar(
            dimension_scores, model_names, dimension_names
        )

        # Verify it returns a base64 string
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify it's valid base64 that decodes to a valid PNG
        img_data = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_data))
        assert img.format == "PNG"

    def test_varying_dimension_scores(self):
        """Test radar chart with varying scores across dimensions."""
        dimension_scores = {
            "model1": {
                "Array": 90.0,
                "Graph": 30.0,
                "Dynamic Programming": 70.0,
                "Greedy": 50.0,
                "Math": 80.0,
                "String": 60.0,
                "Other": 40.0,
            }
        }
        model_names = ["model1"]
        dimension_names = list(ALL_DIMENSIONS)

        result = self.chart_gen.generate_capability_radar(
            dimension_scores, model_names, dimension_names
        )

        # Verify it returns valid PNG
        assert isinstance(result, str)
        img_data = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_data))
        assert img.format == "PNG"

    def test_empty_scores_returns_valid_chart(self):
        """Test that empty scores still produces a valid chart."""
        dimension_scores = {"model1": {dim: 0.0 for dim in ALL_DIMENSIONS}}
        model_names = ["model1"]
        dimension_names = list(ALL_DIMENSIONS)

        result = self.chart_gen.generate_capability_radar(
            dimension_scores, model_names, dimension_names
        )

        # Should still produce valid output
        assert isinstance(result, str)
        img_data = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_data))
        assert img.format == "PNG"

    def test_max_scores_returns_valid_chart(self):
        """Test that maximum scores produce a valid chart."""
        dimension_scores = {"model1": {dim: 100.0 for dim in ALL_DIMENSIONS}}
        model_names = ["model1"]
        dimension_names = list(ALL_DIMENSIONS)

        result = self.chart_gen.generate_capability_radar(
            dimension_scores, model_names, dimension_names
        )

        # Should produce valid output
        assert isinstance(result, str)
        img_data = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_data))
        assert img.format == "PNG"

    def test_four_models_uses_all_colors(self):
        """Test that up to 4 models can be displayed with different colors."""
        dimension_scores = {
            f"model{i}": {dim: 50.0 + (i * 10) for dim in ALL_DIMENSIONS}
            for i in range(1, 5)
        }
        model_names = [f"model{i}" for i in range(1, 5)]
        dimension_names = list(ALL_DIMENSIONS)

        result = self.chart_gen.generate_capability_radar(
            dimension_scores, model_names, dimension_names
        )

        # Should successfully generate chart with 4 models
        assert isinstance(result, str)
        img_data = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_data))
        assert img.format == "PNG"

    def test_partial_dimension_data(self):
        """Test radar chart when some dimensions have no data."""
        dimension_scores = {
            "model1": {
                "Array": 80.0,
                "Graph": 60.0,
                "Dynamic Programming": 0.0,  # No data
                "Greedy": 0.0,  # No data
                "Math": 70.0,
                "String": 50.0,
                "Other": 0.0,  # No data
            }
        }
        model_names = ["model1"]
        dimension_names = list(ALL_DIMENSIONS)

        result = self.chart_gen.generate_capability_radar(
            dimension_scores, model_names, dimension_names
        )

        # Should still produce valid chart
        assert isinstance(result, str)
        img_data = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_data))
        assert img.format == "PNG"

