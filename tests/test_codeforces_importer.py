"""Offline tests for Codeforces API and statement conversion."""

from unittest.mock import Mock

from src.importers.codeforces import CodeforcesImporter


class Response:
    def __init__(self, payload=None, text="", status_code=200):
        self._payload = payload
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._payload


def _statement():
    return """
    <div class="problem-statement">
      <div class="header"><div class="title">A. Add One</div></div>
      <div class="statement"><p>Given x, output x plus one.</p></div>
      <div class="input-specification"><div class="section-title">Input</div><p>An integer x.</p></div>
      <div class="output-specification"><div class="section-title">Output</div><p>The answer.</p></div>
      <div class="sample-tests"><div class="sample-test">
        <div class="input"><div class="title">Input</div><pre>1</pre></div>
        <div class="output"><div class="title">Output</div><pre>2</pre></div>
      </div></div>
    </div>
    """


def test_fetch_filters_and_transforms_public_problem():
    session = Mock()
    session.get.side_effect = [
        Response({"status": "OK", "result": {"problems": [
            {"contestId": 1234, "index": "A", "name": "Add One", "rating": 800, "tags": ["dp"]},
            {"contestId": 1234, "index": "B", "name": "Hard", "rating": 2200, "tags": ["graphs"]},
        ]}}),
        Response(text=_statement()),
    ]
    importer = CodeforcesImporter(session=session, contest=1234, max_rating=1400)

    raw = importer.fetch_problems("codeforces-api")
    problems = importer.transform_to_schema(raw)

    assert [problem["index"] for problem in raw] == ["A"]
    assert len(problems) == 1
    problem = problems[0]
    assert problem.problem_id == "codeforces_1234_A"
    assert problem.difficulty == "easy"
    assert problem.tags == ["dynamic-programming"]
    assert problem.input_output_mode == "stdin_stdout"
    assert problem.public_test_cases[0].input == "1"
    assert problem.public_test_cases[0].expected_output == "2"
    assert problem.source_url.endswith("/1234/A")


def test_rating_and_tag_filters_are_applied_before_detail_fetch():
    session = Mock()
    session.get.side_effect = [
        Response({"status": "OK", "result": {"problems": [
            {"contestId": 1, "index": "A", "name": "DP", "rating": 1600, "tags": ["dp"]},
            {"contestId": 1, "index": "B", "name": "Math", "rating": 1600, "tags": ["math"]},
        ]}}),
        Response(text=_statement()),
    ]
    importer = CodeforcesImporter(session=session, tags=["dp"], min_rating=1500, max_rating=1700)
    raw = importer.fetch_problems("codeforces-api")
    assert [item["index"] for item in raw] == ["A"]
    assert session.get.call_count == 2


def test_missing_statement_is_marked_for_manual_completion():
    importer = CodeforcesImporter()
    problem = importer.transform_to_schema([
        {
            "contestId": 9, "index": "C", "name": "No Statement", "rating": 2300,
            "tags": ["graphs"], "_statement_error": "rate limited",
        }
    ])[0]
    assert problem.needs_manual_completion is True
    assert problem.public_test_cases == []
    assert "rate limited" in problem.manual_completion_notes[0]


def test_difficulty_mapping_and_api_failures():
    assert CodeforcesImporter.map_difficulty(1400) == "easy"
    assert CodeforcesImporter.map_difficulty(1500) == "medium"
    assert CodeforcesImporter.map_difficulty(2200) == "hard"
    assert CodeforcesImporter.map_difficulty(None) == "medium"

    session = Mock()
    session.get.return_value = Response({"status": "FAILED", "comment": "limit"})
    importer = CodeforcesImporter(session=session)
    try:
        importer.fetch_problems("codeforces-api")
    except RuntimeError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("API failure must be surfaced")
