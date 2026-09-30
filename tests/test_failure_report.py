"""Focused tests for failure-mode report denominators and rendering."""

from src.failure_report import (
    FAILURE_MODES,
    render_failure_mode_chart,
    render_failure_mode_markdown,
    summarize_failure_modes,
)


def test_summary_counts_modes_and_tag_denominators_without_unrun_rows():
    problem_info = {
        "p1": {"tags": ["graph"]},
        "p2": {"tags": ["graph", "dp"]},
        "p3": {"tags": ["graph"]},
        "p4": {"tags": ["graph", "dp"]},
    }
    results = [
        {"problem_id": "p1", "status": "failed", "failure_mode": "syntax_error"},
        {"problem_id": "p2", "status": "success"},
        {"problem_id": "p3", "status": "failed", "failure_mode": "timeout"},
        {"problem_id": "p4", "status": "failed", "failure_mode": "logic_error"},
        {"problem_id": "p5", "status": "budget_exhausted", "failure_mode": "unknown"},
        {"problem_id": "p6", "status": "unsupported", "failure_mode": "unknown"},
        {"problem_id": "p7", "status": "cancelled", "failure_mode": "unknown"},
        {"problem_id": "p7b", "status": "canceled", "failure_mode": "unknown"},
        {"problem_id": "p8"},
        {"problem_id": "p9", "status": "unrecognized"},
        {"problem_id": "p10", "status": []},
        {"problem_id": "p11", "status": "error", "evaluation_completed": False,
         "tags": ["graph"], "error_message": "Task unit did not produce a result"},
    ]

    summary = summarize_failure_modes(results, problem_info)

    assert summary["total_evaluated"] == 4
    assert summary["total_failures"] == 3
    assert sum(values["count"] for values in summary["categories"].values()) == 3
    assert summary["categories"]["syntax_error"] == {"count": 1, "share": 0.3333}
    assert tuple(summary["categories"]) == FAILURE_MODES
    assert summary["by_tags"]["graph"] == {
        "evaluated": 4,
        "failures": 3,
        "failure_rate": 0.75,
        "categories": {"syntax_error": 1, "logic_error": 1, "timeout": 1},
    }
    assert summary["by_tags"]["dp"]["evaluated"] == 2
    assert summary["by_tags"]["dp"]["failure_rate"] == 0.5
    assert [item["tag"] for item in summary["top_weaknesses"]] == ["graph"]
    assert summary["top_weaknesses"][0]["dominant_mode"] == "syntax_error"


def test_missing_recorded_mode_uses_classifier_for_historical_results():
    summary = summarize_failure_modes(
        [
            {
                "problem_id": "legacy",
                "status": "failed",
                "final_result": {"status": "syntax_error", "error_message": "SyntaxError"},
            }
        ]
    )
    assert summary["categories"]["syntax_error"]["count"] == 1
    assert summary["categories"]["unknown"]["count"] == 0


def test_weakness_ranking_requires_three_evaluations_and_is_descriptive():
    results = [
        {"problem_id": "a1", "status": "failed", "failure_mode": "logic_error", "tags": ["a"]},
        {"problem_id": "a2", "status": "failed", "failure_mode": "logic_error", "tags": ["a"]},
        {"problem_id": "b1", "status": "failed", "failure_mode": "timeout", "tags": ["b"]},
        {"problem_id": "b2", "status": "failed", "failure_mode": "timeout", "tags": ["b"]},
        {"problem_id": "b3", "status": "success", "tags": ["b"]},
    ]
    summary = summarize_failure_modes(results)
    assert summary["by_tags"]["a"]["failure_rate"] == 1.0
    assert summary["top_weaknesses"] == [
        {
            "tag": "b",
            "evaluated": 3,
            "failures": 2,
            "failure_rate": 0.6667,
            "dominant_mode": "timeout",
            "dominant_count": 2,
        }
    ]
    markdown = render_failure_mode_markdown(summary)
    assert "至少 3 条已评估记录" in markdown
    assert "小样本不足以推断" in markdown
    assert "2 / 3" in markdown


def test_markdown_escapes_dataset_tags_and_chart_is_png():
    summary = summarize_failure_modes(
        [
            {
                "problem_id": "x",
                "status": "failed",
                "failure_mode": "boundary_condition",
                "tags": ["a|<unsafe>"],
            }
        ]
    )
    markdown = render_failure_mode_markdown(summary)
    assert "a\\|&lt;unsafe&gt;" in markdown
    assert "边界条件遗漏" in markdown
    image = render_failure_mode_chart(summary)
    assert image is not None and image.startswith(b"\x89PNG\r\n\x1a\n")


def test_no_failures_report_has_no_chart_or_weakness():
    summary = summarize_failure_modes([{"problem_id": "ok", "status": "success"}])
    assert summary["total_evaluated"] == 1
    assert summary["total_failures"] == 0
    assert summary["top_weaknesses"] == []
    assert render_failure_mode_chart(summary) is None
    assert "当前没有可分类的失败记录" in render_failure_mode_markdown(summary)
