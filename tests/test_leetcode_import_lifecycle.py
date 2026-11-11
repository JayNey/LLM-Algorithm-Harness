"""LeetCode fetch → transform → report/CLI lifecycle regressions (offline)."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.importers.leetcode import LeetCodeImporter
from src.main import main


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = payload or {}

    def json(self):
        return self.payload


def _question():
    return json.loads(
        (Path(__file__).parent / "fixtures/leetcode_questions.json").read_text(encoding="utf-8")
    )[0]


def _batch_responses(statuses):
    questions = [
        {"titleSlug": f"problem-{index}", "questionFrontendId": str(index)}
        for index in range(1, len(statuses) + 1)
    ]
    responses = [Response(payload={"data": {"problemsetQuestionListV2": {"questions": questions}}})]
    for index, status in enumerate(statuses, 1):
        if status == 200:
            question = {**_question(), "questionFrontendId": str(index)}
            responses.append(Response(payload={"data": {"question": question}}))
        else:
            responses.extend([Response(status)] * (2 if status >= 500 else 1))
    return responses


def _importer(responses):
    session = Mock()
    session.post.side_effect = responses
    return LeetCodeImporter(session=session, retries=1, sleep=lambda _: None)


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("statuses", [(200, 404), (200, 503), (404, 404), (503, 503), (200, 200)])
@pytest.mark.parametrize("preview", [True, False])
def test_cli_fetch_transform_report_and_exit(
    statuses, strict, preview, tmp_path, monkeypatch, capsys
):
    # Keep main() from installing a process-global handler on pytest capture streams.
    monkeypatch.setattr("src.main.setup_logging", lambda **kwargs: None)
    importer = _importer(_batch_responses(statuses))
    real_init = LeetCodeImporter.__init__

    def offline_init(self):
        real_init(self, session=importer.session, retries=1, sleep=lambda _: None)

    monkeypatch.setattr(LeetCodeImporter, "__init__", offline_init)
    reports = []
    real_report = LeetCodeImporter.generate_report

    def capture_report(self, *args):
        report = real_report(self, *args)
        reports.append(report)
        return report

    monkeypatch.setattr(LeetCodeImporter, "generate_report", capture_report)
    output = tmp_path / "problems.json"
    argv = [
        "harness",
        "import",
        "--source",
        "leetcode",
        "--tags",
        "array",
        "--import-limit",
        "2",
        "--output",
        str(output),
    ]
    argv.append("--preview" if preview else "--force")
    if strict:
        argv.append("--strict")
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        main()
    failed = sum(status != 200 for status in statuses)
    expected_exit = 2 if failed == 2 else (3 if strict else 1) if failed else 0
    assert exc.value.code == expected_exit
    assert len(reports) == 1
    report = reports[0]
    assert report["summary"]["total_attempted"] == 2
    assert report["summary"]["successful"] == 2 - failed
    assert report["summary"]["failed"] == failed
    assert [item["problem_id"] for item in report["failed_problems"]] == [
        str(i) for i, status in enumerate(statuses, 1) if status != 200
    ]
    for item in report["failed_problems"]:
        status = statuses[int(item["problem_id"]) - 1]
        assert ("not found" if status == 404 else str(status)) in item["error"]
        assert item["slug"] == f"problem-{item['problem_id']}"
    stdout = capsys.readouterr().out
    assert f"  Failed: {failed}" in stdout
    if failed:
        assert "id: 2" in stdout
        assert ("not found" if statuses[1] == 404 else str(statuses[1])) in stdout
    assert output.exists() is not preview
    if not preview:
        assert len(json.loads(output.read_text(encoding="utf-8"))) == 2 - failed
    assert importer.session.post.call_count == 1 + sum(
        2 if status >= 500 else 1 for status in statuses
    )


def test_transform_preserves_fetch_errors_without_accumulating_transform_errors():
    importer = _importer(_batch_responses((200, 404)))
    raw = importer.fetch_problems(tags=["array"], limit=2)
    assert len(importer.transform_failures) == 1
    malformed = {**raw[0], "questionFrontendId": "3", "difficulty": "invalid"}
    assert len(importer.transform_to_schema([raw[0], malformed])) == 1
    assert [failure["problem_id"] for failure in importer.transform_failures] == ["2", "3"]
    assert len(importer.transform_to_schema(raw)) == 1
    assert [failure["problem_id"] for failure in importer.transform_failures] == ["2"]
    assert importer.transform_to_schema([]) == []
    assert [failure["problem_id"] for failure in importer.transform_failures] == ["2"]


@pytest.mark.parametrize("next_mode", ["batch", "single", "empty", "invalid", "network-error"])
def test_new_fetch_round_clears_previous_fetch_and_transform_failures(next_mode):
    responses = _batch_responses((200, 404))
    if next_mode == "batch":
        responses += _batch_responses((200, 200))
    elif next_mode == "single":
        responses += [Response(payload={"data": {"question": _question()}})]
    elif next_mode == "empty":
        responses += _batch_responses(())
    elif next_mode == "network-error":
        responses += [Response(503), Response(503)]
    importer = _importer(responses)
    raw = importer.fetch_problems(tags=["array"], limit=2)
    importer.transform_to_schema([{**raw[0], "difficulty": "invalid"}])
    assert len(importer.transform_failures) == 2
    if next_mode == "invalid":
        with pytest.raises(ValueError):
            importer.fetch_problems("invalid slug!")
    elif next_mode == "network-error":
        with pytest.raises(RuntimeError):
            importer.fetch_problems(tags=["array"])
    else:
        fetched = (
            importer.fetch_problems("two-sum")
            if next_mode == "single"
            else importer.fetch_problems(tags=["array"], limit=2)
        )
        assert importer.transform_failures == []
        importer.transform_to_schema(fetched)
    assert importer.transform_failures == []
