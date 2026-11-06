"""
Interactive debugger main loop using cmd.Cmd.
"""

import cmd
import shlex
from typing import Any

from harness.debug.breakpoint import BreakpointManager
from harness.debug.editor import edit_prompt
from harness.debug.trace import TraceRecorder


class DebugSessionExit(BaseException):
    """Unwind a paused strategy without triggering its execution-error handlers."""


class Debugger(cmd.Cmd):
    """
    Interactive debugger for stepping through strategy execution.

    Provides commands for controlling execution flow, inspecting state,
    and modifying behavior during debugging sessions.
    """

    intro = """
╔══════════════════════════════════════════════════════════════╗
║          Interactive Debug Mode                              ║
╚══════════════════════════════════════════════════════════════╝

Type 'help' or '?' to list commands.
Type 'help <command>' for detailed help on a specific command.
    """.strip()

    prompt = "(debug) "
    _parameter_ranges = {
        "temperature": (float, 0.0, 2.0),
        "max_tokens": (int, 100, 8000),
        "max_rounds": (int, 1, 10),
    }

    def __init__(
        self,
        breakpoint_manager: BreakpointManager,
        trace_recorder: TraceRecorder,
    ):
        """
        Initialize debugger.

        Args:
            breakpoint_manager: Breakpoint manager instance
            trace_recorder: Trace recorder instance
        """
        super().__init__()
        self.breakpoint_manager = breakpoint_manager
        self.trace_recorder = trace_recorder
        self._step = False
        self._paused = False
        self._skip = False
        self.should_exit = False
        self.current_prompt: str | None = None
        self.modified_prompt: str | None = None
        self.injected_text: str | None = None
        self.param_overrides: dict[str, Any] = {}
        self.strategy = None  # Set externally by CLI
        self.problem = None  # Set externally by CLI
        self.result = None

    # ===== Execution control commands =====

    def do_run(self, arg: str) -> bool:
        """Execute the strategy on the problem."""
        if self._paused:
            print("Strategy already running. Use next, continue or skip.")
            return False
        return self._run(step=False)

    def _run(self, *, step: bool) -> bool:
        if not self.strategy or not self.problem:
            print("✗ Strategy or problem not initialized")
            return False

        self.result = None
        self._step = step
        print(f"Running strategy on problem: {self.problem.problem_id}")
        try:
            self.result = self.strategy.execute(self.problem)
            print("\n✓ Execution completed")
            print(f"  Success: {self.result.success}")
            attempts = len(self.result.iterations)
            if self.result.success:
                print(f"  Solution found in {attempts} attempt(s)")
            else:
                print(f"  Failed after {attempts} attempt(s)")
        except DebugSessionExit:
            return True
        except Exception as e:
            print(f"✗ Execution failed: {self.trace_recorder.redact(str(e))}")
        finally:
            self._step = False
            self.current_prompt = None
        return False

    def pause(self, location: str, detail: str) -> bool:
        """Pause if stepping or at an enabled breakpoint. Return whether to skip."""
        if not (self._step or self.breakpoint_manager.should_break(location)):
            return False
        self._step = False
        self._skip = False
        self._paused = True
        print(f"\n⊙ Breakpoint hit at '{location}'")
        print(self.trace_recorder.redact(detail))
        try:
            self.cmdloop(intro="")
        finally:
            self._paused = False

        if self.should_exit:
            self.trace_recorder.record_intervention("quit", location)
            raise DebugSessionExit
        if self._skip:
            self.trace_recorder.record_intervention("skip", location)
        return self._skip

    def do_next(self, arg: str) -> bool:
        """Execute the next step and pause."""
        print("Executing next step...")
        if not self._paused:
            return self._run(step=True)
        self._step = True
        return True

    def do_continue(self, arg: str) -> bool:
        """Continue execution until next breakpoint or completion."""
        print("Continuing to next breakpoint...")
        if not self._paused:
            return self._run(step=False)
        return True

    def do_skip(self, arg: str) -> bool:
        """Skip the current step and continue."""
        if not self._paused:
            print("Skip is available at a breakpoint.")
            return False
        print("Skipping current step...")
        self._skip = True
        return True

    # ===== Breakpoint management =====

    def do_break(self, arg: str) -> None:
        """
        Enable a breakpoint at the specified location.
        Usage: break <location>
        Locations: generate, execute, feedback
        """
        if not arg:
            print("Usage: break <location>")
            print("Available locations: generate, execute, feedback")
            return

        location = arg.strip()
        if self.breakpoint_manager.enable(location):
            print(f"✓ Breakpoint enabled at '{location}'")
        else:
            print(f"✗ Invalid location '{location}'")
            print("Available locations: generate, execute, feedback")

    def do_unbreak(self, arg: str) -> None:
        """
        Disable a breakpoint at the specified location.
        Usage: unbreak <location>
        """
        if not arg:
            print("Usage: unbreak <location>")
            return

        location = arg.strip()
        if self.breakpoint_manager.disable(location):
            print(f"✓ Breakpoint disabled at '{location}'")
        else:
            print(f"✗ Invalid location '{location}'")

    def do_breakpoints(self, arg: str) -> None:
        """List all enabled breakpoints."""
        enabled = self.breakpoint_manager.get_enabled()
        if enabled:
            print("Enabled breakpoints:")
            for loc in sorted(enabled):
                print(f"  - {loc}")
        else:
            print("No breakpoints enabled")

    # ===== Prompt and parameter modification =====

    def do_edit_prompt(self, arg: str) -> None:
        """
        Edit the prompt for the next round.
        Opens your $EDITOR or provides inline input mode.
        """
        current_prompt = arg or self.modified_prompt or self.current_prompt
        if current_prompt is None:
            current_prompt = (
                self.strategy.build_base_prompt(self.problem)
                if self.strategy and self.problem
                else "# Enter your prompt here"
            )

        print("\nOpening prompt editor...")
        edited = edit_prompt(current_prompt)

        if edited and edited != current_prompt:
            self.modified_prompt = edited
            print("\n✓ Prompt modified. New prompt preview:")
            print("─" * 60)
            preview = self.trace_recorder.redact(edited)
            print(preview[:200] + ("..." if len(preview) > 200 else ""))
            print("─" * 60)
        else:
            print("\n✗ Prompt not modified")

    def do_set(self, arg: str) -> None:
        """
        Set a strategy parameter.
        Usage: set <param> <value>
        Example: set temperature 0.9
        """
        if not arg:
            print("Usage: set <param> <value>")
            print("\nCurrent overrides:")
            if self.param_overrides:
                for param, value in self.param_overrides.items():
                    print(f"  {param} = {value}")
            else:
                print("  (none)")
            return

        try:
            parts = shlex.split(arg)
        except ValueError:
            print("Usage: set <param> <value>")
            return
        if len(parts) != 2:
            print("Usage: set <param> <value>")
            return

        param, value_str = parts

        supported = self._parameter_ranges.copy()
        if not self.strategy or self.strategy.config.name not in (
            "multi_round_feedback",
            "reflexion",
        ):
            supported.pop("max_rounds")
        try:
            convert, minimum, maximum = supported[param]
            value = convert(value_str)
        except (KeyError, ValueError):
            value = None
        if value is None or not minimum <= value <= maximum:
            ranges = ", ".join(f"{name} [{lo}, {hi}]" for name, (_, lo, hi) in supported.items())
            print(f"✗ Invalid parameter or value. Supported ranges: {ranges}")
            return

        self.param_overrides[param] = value
        print(f"✓ Set {param} = {value}")
        if param == "max_rounds" and self._paused:
            print("The round limit takes effect on the next run.")

    def do_inject(self, arg: str) -> None:
        """
        Inject custom text into the next prompt.
        Usage: inject "<text>"
        """
        if not arg:
            print('Usage: inject "<text>"')
            return

        # Remove quotes if present
        text = arg.strip().strip('"').strip("'")
        self.injected_text = text
        print("✓ Will inject text into next prompt:")
        print(f"  {self.trace_recorder.redact(text)[:100]}")

    def precmd(self, line: str) -> str:
        command, _, arguments = line.partition(" ")
        if command == "edit-prompt":
            return f"edit_prompt {arguments}"
        return line

    # ===== Trace inspection =====

    def do_trace(self, arg: str) -> None:
        """
        Display execution trace.
        Usage: trace [round_number]
        Without arguments: shows summary of all rounds
        With round number: shows detailed info for that round
        """
        if not arg:
            print(self.trace_recorder.display_summary())
        else:
            try:
                round_num = int(arg.strip())
                print(self.trace_recorder.display_round(round_num))
            except ValueError:
                print(f"Invalid round number: {arg}")

    def do_export(self, arg: str) -> None:
        """
        Export trace to JSON file.
        Usage: export <filepath>
        """
        if not arg:
            print("Usage: export <filepath>")
            return

        filepath = arg.strip()
        if self.trace_recorder.export_json(filepath):
            print(f"✓ Trace exported to {filepath}")
        else:
            print(f"✗ Failed to export trace to {filepath}")

    # ===== Exit commands =====

    def do_exit(self, arg: str) -> bool:
        """Exit the debugging session."""
        return self._handle_exit()

    def do_quit(self, arg: str) -> bool:
        """Exit the debugging session."""
        return self._handle_exit()

    def do_EOF(self, arg: str) -> bool:
        """Handle Ctrl+D to exit."""
        print()  # New line after EOF
        return self._handle_exit()

    def _handle_exit(self) -> bool:
        print("\nExiting debug session...")
        self.should_exit = True
        return True

    def save_trace_on_exit(self) -> None:
        if not self.trace_recorder.get_round_count():
            return
        try:
            if input("\nSave trace before exiting? (y/n): ").strip().lower() not in ("y", "yes"):
                return
            filepath = input("Enter filepath (default: trace.json): ").strip() or "trace.json"
        except EOFError:
            return
        self.do_export(filepath)

    # ===== Helper commands =====

    def do_status(self, arg: str) -> None:
        """Show current debugging status."""
        print("\n" + "=" * 60)
        print("Debugging Status")
        print("=" * 60)

        # Breakpoints
        enabled = self.breakpoint_manager.get_enabled()
        print(f"Breakpoints: {', '.join(enabled) if enabled else 'none'}")

        # Rounds completed
        print(f"Rounds completed: {self.trace_recorder.get_round_count()}")

        # Parameter overrides
        if self.param_overrides:
            print("Parameter overrides:")
            for param, value in self.param_overrides.items():
                print(f"  {param} = {value}")
        else:
            print("Parameter overrides: none")

        # Modifications pending
        if self.modified_prompt:
            print("Prompt modification: pending")
        if self.injected_text:
            print(f"Injected text: {self.trace_recorder.redact(self.injected_text)[:50]}...")

        print("=" * 60 + "\n")

    def emptyline(self) -> bool:
        """Override to do nothing on empty line instead of repeating last command."""
        return False

    def default(self, line: str) -> None:
        """Handle unknown commands."""
        print(f"Unknown command: {line}")
        print("Type 'help' for available commands.")
