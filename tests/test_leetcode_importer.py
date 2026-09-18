"""Offline and network-bound tests for the LeetCode public importer."""

import json
from pathlib import Path

import pytest

from src.importers.leetcode import LeetCodeImporter


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "leetcode_questions.json"


def fixture_questions():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_source_accepts_url_and_slug():
    assert LeetCodeImporter.parse_source("two-sum")[0] == "two-sum"
    assert LeetCodeImporter.parse_source(
        "https://leetcode.com/problems/two-sum/description/?x=1"
    ) == ("two-sum", "https://leetcode.com/problems/two-sum/")


def test_parse_source_rejects_other_hosts():
    with pytest.raises(ValueError, match="Unsupported LeetCode host"):
        LeetCodeImporter.parse_source("https://example.com/problems/two-sum")


def test_clean_html_preserves_code_formula_and_constraints():
    content = LeetCodeImporter.clean_html_content(
        "<p>Use <code>nums</code>.</p><pre><code>if x &lt; 2:\n  return x</code></pre>"
        "<p>1 &lt;= n &lt;= 10<sup>4</sup></p>"
    )

    assert "`nums`" in content
    assert "if x < 2:" in content
    assert "10^4" in content


def test_offline_fixtures_cover_five_shapes_with_exact_results():
    problems = LeetCodeImporter().transform_to_schema(fixture_questions())

    assert len(problems) == 5
    assert problems[0].entry_point == "Solution.twoSum(nums, target)"
    assert problems[0].public_test_cases[0].expected_output == [0, 1]
    assert problems[1].public_test_cases[0].input["nums"] == [2, 3, -2, 4]
    assert problems[1].public_test_cases[0].expected_output == 6
    assert problems[2].public_test_cases[0].expected_output is True
    assert problems[3].public_test_cases[0].input["graph"] == [[1, 2, 3], [0], [0], [0]]
    assert problems[4].needs_manual_completion is True
    assert problems[4].public_test_cases == []


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_fetch_uses_slug_graphql_and_retries_transient_errors():
    question = fixture_questions()[0]
    session = FakeSession(
        [
            FakeResponse(503, {}),
            FakeResponse(200, {"data": {"question": question}}),
        ]
    )
    importer = LeetCodeImporter(session=session, retries=1, sleep=lambda _: None)

    fetched = importer.fetch_problems("two-sum")

    assert fetched[0]["_source_slug"] == "two-sum"
    assert len(session.calls) == 2
    assert session.calls[0][1]["json"]["variables"] == {"titleSlug": "two-sum"}


def test_fetch_rejects_graphql_errors_without_retry():
    session = FakeSession([FakeResponse(200, {"errors": [{"message": "restricted"}]})])
    importer = LeetCodeImporter(session=session, retries=2, sleep=lambda _: None)

    with pytest.raises(ValueError, match="GraphQL error"):
        importer.fetch_problems("design-twitter")

    assert len(session.calls) == 1


def test_transform_keeps_valid_items_when_one_item_is_malformed():
    importer = LeetCodeImporter()
    valid_item = fixture_questions()[0]
    malformed_item = {"title": "bad difficulty", "difficulty": "super-hard"}

    problems = importer.transform_to_schema([valid_item, malformed_item])

    assert len(problems) == 1
    assert len(importer.transform_failures) == 1
    assert importer.transform_failures[0]["index"] == 1


@pytest.mark.integration
def test_optional_online_leetcode_import():
    """Opt-in smoke test; CI remains independent of live LeetCode availability."""
    if not __import__("os").getenv("RUN_LEETCODE_ONLINE"):
        pytest.skip("set RUN_LEETCODE_ONLINE=1 to run the live public endpoint check")
    try:
        import requests  # noqa: F401
    except ImportError:
        pytest.skip("requests/certifi is not installed in this minimal test environment")
    problems = LeetCodeImporter(timeout=10, retries=1).fetch_problems("two-sum")
    assert problems and problems[0]["title"]
