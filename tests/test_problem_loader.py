"""
Tests for ProblemLoader.
"""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models import Problem, TestCase
from src.problem_loader import ProblemLoader


@pytest.fixture
def problem_loader():
    """ProblemLoader fixture."""
    return ProblemLoader()


@pytest.fixture
def sample_dataset():
    """Sample dataset fixture."""
    return [
        {
            "problem_id": "test-001",
            "title": "Two Sum",
            "description": "Find two numbers that add up to target",
            "difficulty": "easy",
            "tags": ["array", "hash-table"],
            "test_cases": [
                {"input": {"nums": [2, 7, 11, 15], "target": 9}, "expected_output": [0, 1]}
            ],
        },
        {
            "problem_id": "test-002",
            "title": "Reverse String",
            "description": "Reverse a string",
            "difficulty": "easy",
            "tags": ["string"],
            "test_cases": [
                {"input": {"s": "hello"}, "expected_output": "olleh"}
            ],
        },
        {
            "problem_id": "test-003",
            "title": "Binary Search",
            "description": "Search in sorted array",
            "difficulty": "medium",
            "tags": ["array", "binary-search"],
            "test_cases": [
                {"input": {"nums": [1, 2, 3, 4, 5], "target": 3}, "expected_output": 2}
            ],
        },
    ]


def test_load_valid_dataset(problem_loader, sample_dataset, tmp_path):
    """Test loading valid dataset file."""
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps(sample_dataset))

    problems = problem_loader.load(str(dataset_file))

    assert len(problems) == 3
    assert problems[0].problem_id == "test-001"
    assert problems[1].title == "Reverse String"
    assert problems[2].difficulty == "medium"


def test_load_file_not_found(problem_loader):
    """Test loading non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        problem_loader.load("/path/does/not/exist.json")


def test_load_empty_dataset(problem_loader, tmp_path):
    """Test loading empty dataset raises ValueError."""
    dataset_file = tmp_path / "empty.json"
    dataset_file.write_text(json.dumps([]))

    with pytest.raises(ValueError, match="Dataset is empty"):
        problem_loader.load(str(dataset_file))


def test_load_invalid_json(problem_loader, tmp_path):
    """Test loading malformed JSON raises JSONDecodeError."""
    dataset_file = tmp_path / "invalid.json"
    dataset_file.write_text("{ invalid json }")

    with pytest.raises(json.JSONDecodeError):
        problem_loader.load(str(dataset_file))


def test_load_non_array_json(problem_loader, tmp_path):
    """Test loading non-array JSON raises ValueError."""
    dataset_file = tmp_path / "object.json"
    dataset_file.write_text(json.dumps({"key": "value"}))

    with pytest.raises(ValueError, match="must be a JSON array"):
        problem_loader.load(str(dataset_file))


def test_validate_dataset_valid(problem_loader, sample_dataset):
    """Test validating valid dataset."""
    problems = problem_loader.validate_dataset(sample_dataset)

    assert len(problems) == 3
    assert all(isinstance(p, Problem) for p in problems)


def test_validate_dataset_partial_valid(problem_loader, sample_dataset):
    """Test validating dataset with some invalid problems."""
    # Add an invalid problem (missing required field)
    invalid_problem = {
        "problem_id": "invalid",
        # Missing title, description, difficulty, test_cases
    }
    mixed_dataset = sample_dataset + [invalid_problem]

    # Should return valid problems only
    problems = problem_loader.validate_dataset(mixed_dataset)

    assert len(problems) == 3  # Only the valid ones


def test_validate_dataset_all_invalid(problem_loader):
    """Test validating dataset with all invalid problems raises ValidationError."""
    invalid_dataset = [
        {"problem_id": "bad-1"},  # Missing fields
        {"title": "No ID"},  # Missing problem_id
    ]

    with pytest.raises(ValueError):
        problem_loader.validate_dataset(invalid_dataset)


def test_filter_problems_by_difficulty(problem_loader, sample_dataset, tmp_path):
    """Test filtering problems by difficulty."""
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps(sample_dataset))

    problems = problem_loader.load(str(dataset_file))
    easy_problems = problem_loader.filter_problems(problems, difficulty="easy")

    assert len(easy_problems) == 2
    assert all(p.difficulty == "easy" for p in easy_problems)


def test_filter_problems_by_tags(problem_loader, sample_dataset, tmp_path):
    """Test filtering problems by tags."""
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps(sample_dataset))

    problems = problem_loader.load(str(dataset_file))
    array_problems = problem_loader.filter_problems(problems, tags=["array"])

    assert len(array_problems) == 2
    assert all("array" in p.tags for p in array_problems)


def test_filter_problems_by_limit(problem_loader, sample_dataset, tmp_path):
    """Test filtering problems with limit."""
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps(sample_dataset))

    problems = problem_loader.load(str(dataset_file))
    limited_problems = problem_loader.filter_problems(problems, limit=2)

    assert len(limited_problems) == 2


def test_filter_problems_combined(problem_loader, sample_dataset, tmp_path):
    """Test filtering with multiple criteria."""
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps(sample_dataset))

    problems = problem_loader.load(str(dataset_file))
    filtered = problem_loader.filter_problems(
        problems, difficulty="easy", tags=["array"], limit=1
    )

    assert len(filtered) == 1
    assert filtered[0].difficulty == "easy"
    assert "array" in filtered[0].tags


def test_filter_problems_no_match(problem_loader, sample_dataset, tmp_path):
    """Test filtering with no matching problems."""
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps(sample_dataset))

    problems = problem_loader.load(str(dataset_file))
    filtered = problem_loader.filter_problems(problems, difficulty="hard")

    assert len(filtered) == 0


def test_load_from_dict_valid(problem_loader):
    """Test loading single problem from dict."""
    data = {
        "problem_id": "test-001",
        "title": "Test",
        "description": "Description",
        "difficulty": "easy",
        "tags": ["test"],
        "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
    }

    problem = problem_loader.load_from_dict(data)

    assert isinstance(problem, Problem)
    assert problem.problem_id == "test-001"


def test_load_from_dict_invalid(problem_loader):
    """Test loading invalid problem from dict raises ValidationError."""
    data = {
        "problem_id": "test-001",
        # Missing required fields
    }

    with pytest.raises((ValueError, ValidationError)):
        problem_loader.load_from_dict(data)
