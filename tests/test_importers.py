"""
Integration tests for problem importers.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.importers.local_json import LocalJsonImporter
from src.importers.mock import MockPlatformImporter
from src.models import Problem


class TestLocalJsonImporter:
    """Test LocalJsonImporter functionality."""

    def test_fetch_problems_success(self, tmp_path):
        """Test successful problem fetching from JSON file."""
        # Create test JSON file
        test_data = [
            {
                "problem_id": "test-001",
                "title": "Test Problem",
                "description": "A test problem",
                "difficulty": "easy",
                "tags": ["test"],
                "source_platform": "test",
                "public_test_cases": [
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            }
        ]
        test_file = tmp_path / "test_problems.json"
        with open(test_file, "w") as f:
            json.dump(test_data, f)

        importer = LocalJsonImporter()
        result = importer.fetch_problems(str(test_file))

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["problem_id"] == "test-001"

    def test_fetch_problems_file_not_found(self):
        """Test fetch with non-existent file."""
        importer = LocalJsonImporter()
        with pytest.raises(FileNotFoundError):
            importer.fetch_problems("nonexistent.json")

    def test_transform_to_schema(self):
        """Test transformation from raw data to Problem objects."""
        raw_data = [
            {
                "problem_id": "test-001",
                "title": "Test",
                "description": "Test problem",
                "difficulty": "easy",
                "source_platform": "test",
                "public_test_cases": [
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            }
        ]

        importer = LocalJsonImporter()
        problems = importer.transform_to_schema(raw_data)

        assert len(problems) == 1
        assert isinstance(problems[0], Problem)
        assert problems[0].problem_id == "test-001"

    def test_detect_duplicates_skip_strategy(self):
        """Test duplicate detection with skip strategy."""
        new_problems = [
            Problem(
                problem_id="test-001",
                title="Test",
                description="Test problem",
                difficulty="easy",
                source_platform="test",
                source_problem_id="001",
                public_test_cases=[
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            )
        ]

        existing_problems = [
            Problem(
                problem_id="test-001",
                title="Existing",
                description="Existing problem",
                difficulty="easy",
                source_platform="test",
                source_problem_id="001",
                public_test_cases=[
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            )
        ]

        importer = LocalJsonImporter()
        final, skipped, overwritten = importer.detect_duplicates(
            new_problems, existing_problems, "skip"
        )

        assert len(skipped) == 1
        assert len(overwritten) == 0
        assert len(final) == 1
        assert final[0].title == "Existing"  # Old version kept

    def test_detect_duplicates_overwrite_strategy(self):
        """Test duplicate detection with overwrite strategy."""
        new_problems = [
            Problem(
                problem_id="test-001",
                title="New",
                description="New problem",
                difficulty="easy",
                source_platform="test",
                source_problem_id="001",
                public_test_cases=[
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            )
        ]

        existing_problems = [
            Problem(
                problem_id="test-001",
                title="Existing",
                description="Existing problem",
                difficulty="easy",
                source_platform="test",
                source_problem_id="001",
                public_test_cases=[
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            )
        ]

        importer = LocalJsonImporter()
        final, skipped, overwritten = importer.detect_duplicates(
            new_problems, existing_problems, "overwrite"
        )

        assert len(skipped) == 0
        assert len(overwritten) == 1
        assert len(final) == 1
        assert final[0].title == "New"  # New version kept

    def test_persist_dataset_atomic_write(self, tmp_path):
        """Test atomic dataset writing."""
        problems = [
            Problem(
                problem_id="test-001",
                title="Test",
                description="Test problem",
                difficulty="easy",
                source_platform="test",
                public_test_cases=[
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            )
        ]

        output_file = tmp_path / "output.json"
        importer = LocalJsonImporter()
        importer.persist_dataset(problems, str(output_file))

        # Verify file was written
        assert output_file.exists()

        # Verify content
        with open(output_file) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["problem_id"] == "test-001"

        # Verify no temp file left behind
        temp_file = tmp_path / "output.json.tmp"
        assert not temp_file.exists()


class TestMockPlatformImporter:
    """Test MockPlatformImporter functionality."""

    def test_fetch_problems_generates_mock_data(self):
        """Test mock problem generation."""
        importer = MockPlatformImporter()
        result = importer.fetch_problems("5")

        assert isinstance(result, list)
        assert len(result) == 5

    def test_transform_to_schema(self):
        """Test transformation of mock data."""
        importer = MockPlatformImporter()
        raw_data = importer.fetch_problems("3")
        problems = importer.transform_to_schema(raw_data)

        assert len(problems) == 3
        assert all(isinstance(p, Problem) for p in problems)
        assert problems[0].source_platform == "mock"


class TestImportIntegration:
    """Integration tests for complete import workflow."""

    def test_full_import_workflow(self, tmp_path):
        """Test complete import workflow from file to persistence."""
        # Create source file
        source_data = [
            {
                "problem_id": "import-001",
                "title": "Import Test",
                "description": "Test import workflow",
                "difficulty": "medium",
                "source_platform": "test-platform",
                "source_problem_id": "001",
                "public_test_cases": [
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            }
        ]
        source_file = tmp_path / "source.json"
        with open(source_file, "w") as f:
            json.dump(source_data, f)

        # Import
        importer = LocalJsonImporter()
        raw_data = importer.fetch_problems(str(source_file))
        problems = importer.transform_to_schema(raw_data)
        valid_problems, failed = importer.validate_problems(problems)

        assert len(valid_problems) == 1
        assert len(failed) == 0

        # Persist
        output_file = tmp_path / "output.json"
        importer.persist_dataset(valid_problems, str(output_file))

        # Verify
        with open(output_file) as f:
            saved_data = json.load(f)
        assert len(saved_data) == 1
        assert saved_data[0]["problem_id"] == "import-001"

    def test_partial_success_scenario(self, tmp_path):
        """Test import with some invalid problems."""
        source_data = [
            {
                "problem_id": "valid-001",
                "title": "Valid",
                "description": "Valid problem",
                "difficulty": "easy",
                "source_platform": "test",
                "public_test_cases": [
                    {"input": {"n": 1}, "expected_output": 1}
                ],
            },
            {
                "problem_id": "invalid-001",
                "title": "Invalid",
                # Missing description (required field)
                "difficulty": "invalid-difficulty",  # Invalid value
            },
        ]
        source_file = tmp_path / "mixed.json"
        with open(source_file, "w") as f:
            json.dump(source_data, f)

        importer = LocalJsonImporter()
        raw_data = importer.fetch_problems(str(source_file))
        problems = importer.transform_to_schema(raw_data)
        valid_problems, failed = importer.validate_problems(problems)

        # Should have 1 valid, 1 failed
        assert len(valid_problems) == 1
        assert len(failed) == 1
        assert valid_problems[0].problem_id == "valid-001"
