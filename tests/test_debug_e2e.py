"""
End-to-end tests for interactive debug mode.

Tests the complete debug workflow including:
- Breakpoint management
- Trace recording
- Parameter configuration
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock

from harness.debug.breakpoint import BreakpointManager
from harness.debug.trace import TraceRecorder


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
            trace_recorder.start_round(i+1, f"Prompt {i+1}")
            trace_recorder.record_response(f"Response {i+1}")
            trace_recorder.record_execution({"status": "success"})
            trace_recorder.complete_round("passed")

        # Export to temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name

        try:
            result = trace_recorder.export_json(temp_path)
            assert result is True

            # Verify file was created and contains valid JSON
            with open(temp_path, 'r') as f:
                data = json.load(f)

            assert 'problem_id' in data
            assert data['problem_id'] == "test_problem"
            assert 'strategy' in data
            assert data['strategy'] == "test_strategy"
            assert 'model' in data
            assert data['model'] == "test_model"
            assert 'rounds' in data
            assert len(data['rounds']) == 3

            # Verify first round data
            assert data['rounds'][0]['round'] == 1
            assert data['rounds'][0]['prompt'] == "Prompt 1"
            assert data['rounds'][0]['response'] == "Response 1"
            assert data['rounds'][0]['status'] == "passed"
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
        assert trace_recorder.rounds[0].user_interventions[0]['type'] == "edit_prompt"
        assert trace_recorder.rounds[0].user_interventions[1]['type'] == "set_parameter"

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
                    expected = other_loc in [l for l in locations if locations.index(l) > locations.index(loc)]
                    if not expected:
                        assert not bp_manager.should_break(other_loc)

    def test_trace_display_methods(self):
        """Test trace display methods produce output."""
        trace_recorder = TraceRecorder("test_problem", "test_strategy", "test_model")

        # Record some rounds
        for i in range(2):
            trace_recorder.start_round(i+1, f"Prompt {i+1}")
            trace_recorder.record_response(f"Response {i+1}")
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
