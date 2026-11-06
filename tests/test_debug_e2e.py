"""
End-to-end tests for interactive debug mode.

Tests the complete debug workflow including:
- Breakpoint management
- Trace recording
- Parameter configuration
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

from harness.debug.breakpoint import BreakpointManager
from harness.debug.trace import TraceRecorder
from src.main import main
from src.models import ExecutionResult
from src.strategies.vanilla import VanillaStrategy


@pytest.fixture
def debug_cli(tmp_path, monkeypatch, sample_problem, mock_llm_client, mock_sandbox_executor):
    dataset = tmp_path / "problems.json"
    dataset.write_text(json.dumps([sample_problem.model_dump(mode="json")]), encoding="utf-8")
    output = tmp_path / "trace.json"
    monkeypatch.setattr("src.llm_client.LLMClient", lambda config: mock_llm_client)
    monkeypatch.setattr(
        "src.sandbox_executor.SandboxExecutor", lambda config: mock_sandbox_executor
    )

    def run(commands, strategy="vanilla"):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "harness",
                "debug",
                "--problem",
                sample_problem.problem_id,
                "--strategy",
                strategy,
                "--model",
                "test-model",
                "--dataset",
                str(dataset),
                "--trace-output",
                str(output),
            ],
        )
        commands = iter(commands)
        calls_at_prompt = []

        def read_command(prompt):
            if prompt.startswith("Save trace"):
                return "n"
            calls_at_prompt.append(
                (mock_llm_client.generate.call_count, mock_sandbox_executor.execute.call_count)
            )
            return next(commands, "quit")

        monkeypatch.setattr("builtins.input", read_command)
        with pytest.raises(SystemExit) as result:
            main()
        assert result.value.code == 0
        return calls_at_prompt, json.loads(output.read_text(encoding="utf-8"))

    return run


@pytest.mark.parametrize(
    ("success", "summary", "trace_status"),
    [
        (True, "Solution found in 1 attempt(s)", "passed"),
        (False, "Failed after 1 attempt(s)", "failed"),
    ],
    ids=["solved", "wrong-answer"],
)
def test_cli_run_summarizes_result_and_keeps_trace_available(
    debug_cli, mock_sandbox_executor, tmp_path, capsys, success, summary, trace_status
):
    if not success:
        sandbox_result = mock_sandbox_executor.execute.return_value
        wrong_answer = sandbox_result.test_results[0].model_copy(
            update={"passed": False, "status": "failed", "actual_output": []}
        )
        mock_sandbox_executor.execute.return_value = sandbox_result.model_copy(
            update={"status": "failed", "all_passed": False, "test_results": [wrong_answer]}
        )

    exported = tmp_path / "run-trace.json"
    _, trace = debug_cli(["run", "trace 1", f"export {exported}", "quit"])

    output = capsys.readouterr().out
    assert "Execution completed" in output
    assert f"Success: {success}" in output
    assert summary in output
    assert "Execution failed" not in output
    assert "Round 1 Details" in output
    assert [round_info["status"] for round_info in trace["rounds"]] == [trace_status]
    assert json.loads(exported.read_text(encoding="utf-8"))["rounds"] == trace["rounds"]


def test_cli_run_summarizes_zero_iterations(debug_cli, monkeypatch, sample_problem, capsys):
    result = ExecutionResult(
        problem_id=sample_problem.problem_id,
        strategy="vanilla",
        generated_code="",
        status="failed",
        iterations=[],
    )
    monkeypatch.setattr(VanillaStrategy, "execute", lambda self, problem: result)

    _, trace = debug_cli(["run", "trace", "quit"])

    output = capsys.readouterr().out
    assert "Execution completed" in output
    assert "Success: False" in output
    assert "Failed after 0 attempt(s)" in output
    assert "Execution failed" not in output
    assert "No rounds recorded yet." in output
    assert trace["total_rounds"] == 0


def test_cli_run_reports_strategy_exception_and_returns_to_prompt(debug_cli, monkeypatch, capsys):
    secret = "test-debug-api-key"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    def fail_building_prompt(self, problem):
        raise RuntimeError(f"prompt construction failed for {secret}")

    monkeypatch.setattr(VanillaStrategy, "build_base_prompt", fail_building_prompt)

    debug_cli(["run", "status", "quit"])

    output = capsys.readouterr().out
    assert "Execution failed: prompt construction failed" in output
    assert "Execution completed" not in output
    assert secret not in output
    assert "Debugging Status" in output


def test_cli_initial_next_steps_and_continue_honors_breakpoint(debug_cli, capsys):
    calls, trace = debug_cli(
        ["break feedback", "next", "trace 1", "next", "continue", "continue", "quit"]
    )
    assert calls == [(0, 0), (0, 0), (1, 0), (1, 0), (1, 0), (1, 1), (1, 1)]
    assert trace["rounds"][0]["status"] == "passed"
    output = capsys.readouterr().out
    assert "Round 1 Details" in output
    assert "Breakpoint hit at 'feedback'" in output


@pytest.mark.parametrize("location", ["generate", "execute"])
def test_cli_quit_at_breakpoint_stops_the_strategy(debug_cli, location, mock_sandbox_executor):
    calls, trace = debug_cli([f"break {location}", "run", "quit"])
    assert calls == [(0, 0), (0, 0), (1, 0)]
    mock_sandbox_executor.execute.assert_not_called()
    assert trace["rounds"][0]["response"]
    assert trace["rounds"][0]["status"] == "cancelled"


@pytest.mark.parametrize("location", ["generate", "execute"])
def test_cli_skip_bypasses_sandbox(debug_cli, location, mock_sandbox_executor):
    _, trace = debug_cli([f"break {location}", "run", "skip", "quit"])
    mock_sandbox_executor.execute.assert_not_called()
    assert trace["rounds"][0]["status"] == "skipped"
    assert any(item["type"] == "skip" for item in trace["rounds"][0]["user_interventions"])


def test_cli_applies_one_time_prompt_changes_and_exports_redacted_trace(
    debug_cli, monkeypatch, mock_llm_client, mock_sandbox_executor, tmp_path, capsys
):
    secret = "secret-debug-session-value"
    prompt = f"REVIEW_EDIT api_key={secret}"
    monkeypatch.setattr("harness.debug.debugger.edit_prompt", lambda text: prompt)
    original_response = mock_llm_client.generate.return_value
    mock_llm_client.generate.return_value = original_response.model_copy(
        update={"text": original_response.text + f"\napi_key={secret}"}
    )
    manual_trace = tmp_path / "manual.json"
    _, trace = debug_cli(
        [
            "set temperature 0.1",
            "set temperature 20",
            "set max_tokens 256",
            "edit-prompt",
            "inject REVIEW_INJECT",
            "run",
            "trace",
            "trace 1",
            f"export {manual_trace}",
            "run",
            "quit",
        ]
    )
    first, second = mock_llm_client.generate.call_args_list
    assert first.args[0] == f"{prompt}\n\nREVIEW_INJECT"
    assert "REVIEW_EDIT" not in second.args[0]
    assert "REVIEW_INJECT" not in second.args[0]
    assert first.kwargs["temperature"] == second.kwargs["temperature"] == 0.1
    assert first.kwargs["max_tokens"] == second.kwargs["max_tokens"] == 256
    assert mock_sandbox_executor.execute.call_count == 2
    assert [item["round"] for item in trace["rounds"]] == [1, 2]
    round_one = trace["rounds"][0]
    assert "REVIEW_INJECT" in round_one["prompt"]
    assert "def solution" in round_one["response"]
    assert round_one["execution_result"]["test_results"][0]["passed"]
    assert round_one["feedback"]
    assert {"set_parameter", "edit_prompt", "inject"} <= {
        item["type"] for item in round_one["user_interventions"]
    }
    assert json.loads(manual_trace.read_text(encoding="utf-8"))["rounds"] == [round_one]
    assert secret not in json.dumps(trace)
    output = capsys.readouterr().out
    assert "Round 1 Details" in output and "Total Rounds: 1" in output
    assert "Success: True" in output and "Execution failed" not in output
    assert secret not in output


def test_cli_max_rounds_limits_multi_round_strategy(debug_cli, mock_sandbox_executor):
    mock_sandbox_executor.execute.return_value = (
        mock_sandbox_executor.execute.return_value.model_copy(
            update={"status": "failed", "all_passed": False}
        )
    )
    _, trace = debug_cli(["set max_rounds 2", "run", "quit"], strategy="multi_round_feedback")
    assert mock_sandbox_executor.execute.call_count == 2
    assert [item["status"] for item in trace["rounds"]] == ["failed", "failed"]
    assert {"type": "set_parameter", "details": "max_rounds = 2"} in trace["rounds"][0][
        "user_interventions"
    ]


def test_cli_quit_at_feedback_preserves_feedback_and_stops_retry(debug_cli, mock_sandbox_executor):
    mock_sandbox_executor.execute.return_value = (
        mock_sandbox_executor.execute.return_value.model_copy(
            update={"status": "failed", "all_passed": False}
        )
    )
    calls, trace = debug_cli(["break feedback", "run", "quit"], strategy="multi_round_feedback")
    assert calls == [(0, 0), (0, 0), (1, 1)]
    assert trace["total_rounds"] == 1
    assert trace["rounds"][0]["execution_result"]["status"] == "failed"
    assert "All passed: False" in trace["rounds"][0]["feedback"]


def test_cli_intercepts_strategy_that_calls_client_directly(debug_cli, mock_llm_client):
    calls, trace = debug_cli(["set temperature 0.2", "next", "quit"], strategy="self_consistency")
    assert calls == [(0, 0), (0, 0), (1, 0)]
    mock_llm_client.generate.assert_called_once()
    assert mock_llm_client.generate.call_args.kwargs["temperature"] == 0.2
    assert trace["rounds"][0]["response"]


def test_cli_feedback_breakpoint_interventions_apply_to_next_request(
    debug_cli, monkeypatch, mock_llm_client, mock_sandbox_executor
):
    mock_sandbox_executor.execute.return_value = (
        mock_sandbox_executor.execute.return_value.model_copy(
            update={"status": "failed", "all_passed": False}
        )
    )
    monkeypatch.setattr("harness.debug.debugger.edit_prompt", lambda text: "EDIT_AT_FEEDBACK")
    _, trace = debug_cli(
        [
            "break feedback",
            "run",
            "set temperature 0.3",
            "edit_prompt",
            "inject INJECT_AT_FEEDBACK",
            "skip",
            "quit",
        ],
        strategy="multi_round_feedback",
    )
    first, second = mock_llm_client.generate.call_args_list
    assert first.kwargs["temperature"] is None
    assert second.kwargs["temperature"] == 0.3
    assert second.args[0] == "EDIT_AT_FEEDBACK\n\nINJECT_AT_FEEDBACK"
    assert trace["rounds"][0]["user_interventions"] == [{"type": "skip", "details": "feedback"}]
    assert trace["rounds"][1]["prompt"] == second.args[0]


def test_cli_export_error_leaves_session_and_automatic_trace_available(debug_cli, tmp_path, capsys):
    _, trace = debug_cli(["run", f"export {tmp_path / 'missing' / 'trace.json'}", "quit"])
    assert "Choose a writable path" in capsys.readouterr().out
    assert trace["total_rounds"] == 1


class TestDebugE2E:
    """End-to-end test for complete debug workflow."""

    def test_breakpoint_management(self):
        """Test breakpoint enable/disable workflow."""
        bp_manager = BreakpointManager()

        # Initially no breakpoints are set
        assert not bp_manager.should_break("generate")
        assert not bp_manager.should_break("execute")
        assert not bp_manager.should_break("feedback")

        # Enable breakpoints
        bp_manager.enable("generate")
        bp_manager.enable("execute")
        bp_manager.enable("feedback")

        # Verify all breakpoints are active
        assert bp_manager.should_break("generate")
        assert bp_manager.should_break("execute")
        assert bp_manager.should_break("feedback")

        # Disable one breakpoint
        bp_manager.disable("generate")
        assert not bp_manager.should_break("generate")
        assert bp_manager.should_break("execute")
        assert bp_manager.should_break("feedback")

    def test_trace_recording(self):
        """Test trace recording functionality."""
        trace_recorder = TraceRecorder("test_problem", "test_strategy", "test_model")

        # Record a round
        trace_recorder.start_round(1, "Test prompt")
        trace_recorder.record_response("Test response")
        trace_recorder.record_code("def test(): pass")
        trace_recorder.record_execution({"status": "success", "output": "OK"})
        trace_recorder.record_feedback("Test feedback")
        trace_recorder.complete_round("passed")

        # Verify round was recorded
        assert len(trace_recorder.rounds) == 1
        assert trace_recorder.rounds[0].round == 1
        assert trace_recorder.rounds[0].prompt == "Test prompt"
        assert trace_recorder.rounds[0].response == "Test response"
        assert trace_recorder.rounds[0].code == "def test(): pass"
        assert trace_recorder.rounds[0].status == "passed"

    def test_trace_export(self):
        """Test trace export to JSON."""
        trace_recorder = TraceRecorder("test_problem", "test_strategy", "test_model")

        # Record multiple rounds
        for i in range(3):
            trace_recorder.start_round(i + 1, f"Prompt {i + 1}")
            trace_recorder.record_response(f"Response {i + 1}")
            trace_recorder.record_execution({"status": "success"})
            trace_recorder.complete_round("passed")

        # Export to temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json", encoding="utf-8"
        ) as f:
            temp_path = f.name

        try:
            result = trace_recorder.export_json(temp_path)
            assert result is True

            # Verify file was created and contains valid JSON
            with open(temp_path, encoding="utf-8") as f:
                data = json.load(f)

            assert "problem_id" in data
            assert data["problem_id"] == "test_problem"
            assert "strategy" in data
            assert data["strategy"] == "test_strategy"
            assert "model" in data
            assert data["model"] == "test_model"
            assert "rounds" in data
            assert len(data["rounds"]) == 3

            # Verify first round data
            assert data["rounds"][0]["round"] == 1
            assert data["rounds"][0]["prompt"] == "Prompt 1"
            assert data["rounds"][0]["response"] == "Response 1"
            assert data["rounds"][0]["status"] == "passed"
        finally:
            # Cleanup
            Path(temp_path).unlink(missing_ok=True)

    def test_trace_user_interventions(self):
        """Test recording user interventions in trace."""
        trace_recorder = TraceRecorder("test_problem", "test_strategy", "test_model")

        trace_recorder.start_round(1, "Test prompt")

        # Add user interventions
        trace_recorder.record_intervention("edit_prompt", "Modified the prompt")
        trace_recorder.record_intervention("set_parameter", "Changed temperature to 0.9")

        trace_recorder.record_response("Test response")
        trace_recorder.complete_round("passed")

        # Verify interventions were recorded
        assert len(trace_recorder.rounds) == 1
        assert len(trace_recorder.rounds[0].user_interventions) == 2
        assert trace_recorder.rounds[0].user_interventions[0]["type"] == "edit_prompt"
        assert trace_recorder.rounds[0].user_interventions[1]["type"] == "set_parameter"

    def test_multiple_breakpoint_locations(self):
        """Test multiple breakpoint locations can be managed independently."""
        bp_manager = BreakpointManager()

        # Test different breakpoint locations
        locations = ["generate", "execute", "feedback"]

        # Enable all
        for loc in locations:
            bp_manager.enable(loc)

        # Verify all are enabled
        for loc in locations:
            assert bp_manager.should_break(loc)

        # Disable each one by one
        for loc in locations:
            bp_manager.disable(loc)
            assert not bp_manager.should_break(loc)

            # Verify others are still enabled
            for other_loc in locations:
                if other_loc != loc:
                    expected = other_loc in [
                        loc_item
                        for loc_item in locations
                        if locations.index(loc_item) > locations.index(loc)
                    ]
                    if not expected:
                        assert not bp_manager.should_break(other_loc)

    def test_trace_display_methods(self):
        """Test trace display methods produce output."""
        trace_recorder = TraceRecorder("test_problem", "test_strategy", "test_model")

        # Record some rounds
        for i in range(2):
            trace_recorder.start_round(i + 1, f"Prompt {i + 1}")
            trace_recorder.record_response(f"Response {i + 1}")
            trace_recorder.complete_round("passed")

        # Test display_summary returns a string
        summary = trace_recorder.display_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "test_problem" in summary

        # Test display_round returns a string
        round_display = trace_recorder.display_round(1)
        assert isinstance(round_display, str)
        assert len(round_display) > 0
        assert "Prompt 1" in round_display
