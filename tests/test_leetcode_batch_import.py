"""Unit tests for LeetCode batch import functionality."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.importers.leetcode import LeetCodeImporter

FIXTURE_PATH = Path(__file__).parent / "fixtures"


def load_fixture(filename):
    """Load a JSON fixture file."""
    return json.loads((FIXTURE_PATH / filename).read_text(encoding="utf-8"))


@pytest.fixture
def mock_session():
    """Mock requests session for batch import tests."""
    session = Mock()
    return session


@pytest.fixture
def importer(mock_session):
    """Create a LeetCodeImporter with mocked session."""
    imp = LeetCodeImporter()
    imp.session = mock_session
    return imp


def test_fetch_question_list_returns_multiple_questions(importer, mock_session):
    """Test that _fetch_question_list returns a list of question metadata."""
    # Arrange
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = load_fixture("leetcode_problemset_list.json")
    mock_session.post.return_value = mock_response

    # Act
    questions = importer._fetch_question_list(tags=["array"], difficulty="easy", limit=10)

    # Assert
    assert len(questions) == 3
    assert questions[0]["titleSlug"] == "two-sum"
    assert questions[0]["questionFrontendId"] == "1"
    assert questions[1]["titleSlug"] == "maximum-product-subarray"
    assert questions[2]["titleSlug"] == "shortest-path-visiting-all-nodes"


def test_fetch_question_list_normalizes_difficulty(importer, mock_session):
    """Test that difficulty is normalized to LeetCode enum format."""
    # Arrange
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = load_fixture("leetcode_problemset_list.json")
    mock_session.post.return_value = mock_response

    # Act
    importer._fetch_question_list(difficulty="easy")

    # Assert
    call_args = mock_session.post.call_args
    payload = call_args[1]["json"]
    assert payload["variables"]["filters"]["difficulty"] == "EASY"


def test_fetch_question_list_validates_difficulty_value(importer):
    """Test that invalid difficulty values raise clear errors."""
    with pytest.raises(ValueError, match="Invalid difficulty.*Must be easy, medium, or hard"):
        importer._fetch_question_list(difficulty="invalid")


def test_fetch_question_list_validates_response_fields(importer, mock_session):
    """Test that missing required fields in response raise clear errors."""
    # Arrange - missing 'questions' field
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"problemsetQuestionList": {}}}
    mock_session.post.return_value = mock_response

    # Act & Assert
    with pytest.raises(ValueError, match="problemsetQuestionList returned no data"):
        importer._fetch_question_list()


def test_fetch_question_list_validates_titleslug_present(importer, mock_session):
    """Test that questions missing titleSlug raise clear errors."""
    # Arrange
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "problemsetQuestionList": {
                "questions": [{"questionFrontendId": "1", "title": "Test"}]  # missing titleSlug
            }
        }
    }
    mock_session.post.return_value = mock_response

    # Act & Assert
    with pytest.raises(ValueError, match="Question missing titleSlug"):
        importer._fetch_question_list()


def test_fetch_question_list_retries_on_429(importer, mock_session):
    """Test that rate limit errors trigger retry with backoff."""
    # Arrange
    mock_response_429 = Mock()
    mock_response_429.status_code = 429
    mock_response_success = Mock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = load_fixture("leetcode_problemset_list.json")
    mock_session.post.side_effect = [mock_response_429, mock_response_success]

    with patch.object(importer, "sleep"):
        # Act
        questions = importer._fetch_question_list()

        # Assert
        assert len(questions) == 3
        assert mock_session.post.call_count == 2


def test_fetch_batch_questions_fetches_all_questions(importer, mock_session):
    """Test that batch mode fetches list then details for each question."""
    # Arrange
    list_response = Mock()
    list_response.status_code = 200
    list_response.json.return_value = load_fixture("leetcode_problemset_list.json")

    detail_responses = []
    question_fixtures = load_fixture("leetcode_questions.json")
    for q in question_fixtures[:3]:
        detail_response = Mock()
        detail_response.status_code = 200
        detail_response.json.return_value = {"data": {"question": q}}
        detail_responses.append(detail_response)

    mock_session.post.side_effect = [list_response] + detail_responses

    with patch.object(importer, "sleep"):
        # Act
        results = importer._fetch_batch_questions(tags=["array"], limit=3)

        # Assert
        assert len(results) == 3
        assert results[0]["_source_slug"] == "two-sum"
        assert mock_session.post.call_count == 4  # 1 list + 3 details


def test_fetch_batch_questions_continues_on_partial_failure(importer, mock_session):
    """Test that batch mode records failures but continues with other questions."""
    # Arrange
    list_response = Mock()
    list_response.status_code = 200
    list_response.json.return_value = load_fixture("leetcode_problemset_list.json")

    # First detail succeeds, second fails (with retries), third succeeds
    detail_response_1 = Mock()
    detail_response_1.status_code = 200
    question_fixtures = load_fixture("leetcode_questions.json")
    detail_response_1.json.return_value = {"data": {"question": question_fixtures[0]}}

    # Second question fails - will retry 2 times (total 3 attempts with default retries=2)
    detail_response_2_fail = Mock()
    detail_response_2_fail.status_code = 500  # Server error

    detail_response_3 = Mock()
    detail_response_3.status_code = 200
    detail_response_3.json.return_value = {"data": {"question": question_fixtures[2]}}

    mock_session.post.side_effect = [
        list_response,
        detail_response_1,  # Question 0 succeeds
        detail_response_2_fail,  # Question 1 fails (attempt 1)
        detail_response_2_fail,  # Question 1 fails (attempt 2)
        detail_response_2_fail,  # Question 1 fails (attempt 3)
        detail_response_3,  # Question 2 succeeds
    ]

    with patch.object(importer, "sleep"):
        # Act
        results = importer._fetch_batch_questions(tags=["array"])

        # Assert
        assert len(results) == 2  # 2 succeeded
        assert len(importer.transform_failures) == 1  # 1 failed
        # The second question (index 1) failed after retries
        assert importer.transform_failures[0]["slug"] == "maximum-product-subarray"
        assert importer.transform_failures[0]["index"] == 1  # Second question (0-indexed)


def test_fetch_batch_questions_adds_delay_between_requests(importer, mock_session):
    """Test that batch mode adds delay between detail requests."""
    # Arrange
    list_response = Mock()
    list_response.status_code = 200
    list_response.json.return_value = load_fixture("leetcode_problemset_list.json")

    question_fixtures = load_fixture("leetcode_questions.json")
    detail_responses = []
    for q in question_fixtures[:3]:
        detail_response = Mock()
        detail_response.status_code = 200
        detail_response.json.return_value = {"data": {"question": q}}
        detail_responses.append(detail_response)

    mock_session.post.side_effect = [list_response] + detail_responses

    with patch.object(importer, "sleep") as mock_sleep:
        # Act
        importer._fetch_batch_questions(tags=["array"])

        # Assert - should sleep between each detail request (N-1 times for N questions)
        assert mock_sleep.call_count == 2  # 3 questions = 2 delays


def test_fetch_problems_batch_mode_with_tags(importer):
    """Test that fetch_problems uses batch mode when tags are provided."""
    # Arrange
    with patch.object(importer, "_fetch_batch_questions") as mock_batch:
        mock_batch.return_value = []

        # Act
        importer.fetch_problems(source=None, tags=["array", "hash-table"])

        # Assert
        mock_batch.assert_called_once_with(
            tags=["array", "hash-table"], difficulty=None, limit=None
        )


def test_fetch_problems_batch_mode_with_difficulty(importer):
    """Test that fetch_problems uses batch mode when difficulty is provided."""
    # Arrange
    with patch.object(importer, "_fetch_batch_questions") as mock_batch:
        mock_batch.return_value = []

        # Act
        importer.fetch_problems(source=None, difficulty="medium", limit=10)

        # Assert
        mock_batch.assert_called_once_with(tags=None, difficulty="medium", limit=10)


def test_fetch_problems_single_mode_ignores_batch_params(importer):
    """Test that single-question import ignores batch parameters."""
    # Arrange
    with patch.object(importer, "_fetch_question_data") as mock_single:
        mock_single.return_value = []

        # Act
        importer.fetch_problems(source="two-sum", tags=["array"], difficulty="easy")

        # Assert
        mock_single.assert_called_once()
        # Verify it was called with slug and canonical_url, not batch params
        call_args = mock_single.call_args
        assert call_args[0][0] == "two-sum"
        assert "https://leetcode.com/problems/two-sum/" in call_args[0][1]


def test_fetch_problems_validates_batch_mode_requires_filters(importer):
    """Test that batch mode without source requires at least one filter."""
    # Act & Assert
    with pytest.raises(ValueError, match="requires either a source.*or batch filters"):
        importer.fetch_problems(source=None)
