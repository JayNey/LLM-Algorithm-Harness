"""
Interactive debugger main loop using cmd.Cmd.
"""

import cmd
import shlex
from typing import Optional
from harness.debug.breakpoint import BreakpointManager
from harness.debug.trace import TraceRecorder
from harness.debug.editor import edit_prompt


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
        self.continue_execution = False
        self.skip_current = False
        self.should_exit = False
        self.modified_prompt: Optional[str] = None
        self.injected_text: Optional[str] = None
        self.param_overrides = {}

    # ===== Execution control commands =====

    def do_next(self, arg):
        """Execute the next step and pause."""
        print("Executing next step...")
        self.continue_execution = True
        return True  # Exit cmdloop

    def do_continue(self, arg):
        """Continue execution until next breakpoint or completion."""
        print("Continuing to next breakpoint...")
        self.continue_execution = True
        # Temporarily disable all breakpoints for this command
        # (handled by caller checking continue_execution flag)
        return True  # Exit cmdloop

    def do_skip(self, arg):
        """Skip the current step and continue."""
        print("Skipping current step...")
        self.skip_current = True
        self.continue_execution = True
        return True  # Exit cmdloop

    # ===== Breakpoint management =====

    def do_break(self, arg):
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

    def do_unbreak(self, arg):
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

    def do_breakpoints(self, arg):
        """List all enabled breakpoints."""
        enabled = self.breakpoint_manager.get_enabled()
        if enabled:
            print("Enabled breakpoints:")
            for loc in sorted(enabled):
                print(f"  - {loc}")
        else:
            print("No breakpoints enabled")

    # ===== Prompt and parameter modification =====

    def do_edit_prompt(self, arg):
        """
        Edit the prompt for the next round.
        Opens your $EDITOR or provides inline input mode.
        """
        # Get current prompt from context (would be passed by wrapper)
        current_prompt = arg if arg else "# Enter your prompt here"

        print("\nOpening prompt editor...")
        edited = edit_prompt(current_prompt)

        if edited and edited != current_prompt:
            self.modified_prompt = edited
            print("\n✓ Prompt modified. New prompt preview:")
            print("─" * 60)
            print(edited[:200] + ("..." if len(edited) > 200 else ""))
            print("─" * 60)
        else:
            print("\n✗ Prompt not modified")

    def do_set(self, arg):
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

        parts = shlex.split(arg)
        if len(parts) != 2:
            print("Usage: set <param> <value>")
            return

        param, value_str = parts

        # Try to convert value to appropriate type
        try:
            # Try int first
            value = int(value_str)
        except ValueError:
            try:
                # Then try float
                value = float(value_str)
            except ValueError:
                # Keep as string
                value = value_str

        self.param_overrides[param] = value
        print(f"✓ Set {param} = {value}")

    def do_inject(self, arg):
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
        print(f"✓ Will inject text into next prompt:")
        print(f"  {text[:100]}")

    # ===== Trace inspection =====

    def do_trace(self, arg):
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

    def do_export(self, arg):
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

    def do_exit(self, arg):
        """Exit the debugging session."""
        return self._handle_exit()

    def do_quit(self, arg):
        """Exit the debugging session."""
        return self._handle_exit()

    def do_EOF(self, arg):
        """Handle Ctrl+D to exit."""
        print()  # New line after EOF
        return self._handle_exit()

    def _handle_exit(self):
        """Handle exit with optional trace save prompt."""
        if self.trace_recorder.get_round_count() > 0:
            response = input("\nSave trace before exiting? (y/n): ").strip().lower()
            if response in ('y', 'yes'):
                filepath = input("Enter filepath (default: trace.json): ").strip()
                if not filepath:
                    filepath = "trace.json"
                if self.trace_recorder.export_json(filepath):
                    print(f"✓ Trace saved to {filepath}")
                else:
                    print(f"✗ Failed to save trace")

        print("\nExiting debug session...")
        self.should_exit = True
        return True  # Exit cmdloop

    # ===== Helper commands =====

    def do_status(self, arg):
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
            print(f"Injected text: {self.injected_text[:50]}...")

        print("=" * 60 + "\n")

    def emptyline(self):
        """Override to do nothing on empty line instead of repeating last command."""
        pass

    def default(self, line):
        """Handle unknown commands."""
        print(f"Unknown command: {line}")
        print("Type 'help' for available commands.")