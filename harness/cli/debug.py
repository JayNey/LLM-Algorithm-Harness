"""
CLI command for interactive debugging.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from src.harness import AlgorithmHarness
from src.problem_loader import ProblemLoader
from src.utils.logging import get_logger
from harness.debug.debugger import Debugger
from harness.debug.breakpoint import BreakpointManager
from harness.debug.trace import TraceRecorder
from harness.debug.strategy_wrapper import DebugStrategyWrapper

logger = get_logger(__name__)


def run_debug_command(args: argparse.Namespace) -> int:
    """
    Run interactive debugging session.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        # Load problem
        problem_loader = ProblemLoader()
        problems = problem_loader.load_problems(args.dataset if hasattr(args, 'dataset') else 'data/problems.json')

        # Find the requested problem
        problem = None
        for p in problems:
            if p.problem_id == args.problem:
                problem = p
                break

        if problem is None:
            print(f"Error: Problem '{args.problem}' not found")
            print("\nAvailable problems:")
            for p in problems[:10]:  # Show first 10
                print(f"  - {p.problem_id}")
            if len(problems) > 10:
                print(f"  ... and {len(problems) - 10} more")
            return 1

        # Initialize components
        breakpoint_manager = BreakpointManager()
        trace_recorder = TraceRecorder(
            problem_id=args.problem,
            strategy_name=args.strategy,
            model_name=args.model
        )

        # Create debugger
        debugger = Debugger(breakpoint_manager, trace_recorder)

        print(f"\n{'='*60}")
        print(f"Interactive Debug Session")
        print(f"{'='*60}")
        print(f"Problem: {problem.problem_id} - {problem.title}")
        print(f"Strategy: {args.strategy}")
        print(f"Model: {args.model}")
        print(f"{'='*60}\n")

        # TODO: Initialize strategy and wrapper
        # This requires loading the full harness configuration
        # For now, just run the debugger loop to verify the CLI works

        print("Note: Full strategy execution integration is pending.")
        print("You can test debugger commands:\n")

        # Start debugger loop
        debugger.cmdloop()

        # Handle trace output if specified
        if hasattr(args, 'trace_output') and args.trace_output:
            if trace_recorder.export_json(args.trace_output):
                print(f"\n✓ Trace saved to {args.trace_output}")
            else:
                print(f"\n✗ Failed to save trace to {args.trace_output}")

        return 0

    except Exception as e:
        logger.error("debug_command_failed", error=str(e), exc_info=True)
        print(f"\nError: {e}")
        return 1


def add_debug_subcommand(subparsers) -> None:
    """
    Add debug subcommand to argument parser.

    Args:
        subparsers: Subparsers object from main parser
    """
    debug_parser = subparsers.add_parser(
        "debug",
        help="Run interactive debugging session for a single problem"
    )

    debug_parser.add_argument(
        "--problem",
        type=str,
        required=True,
        help="Problem ID to debug"
    )

    debug_parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        help="Strategy to use (e.g., vanilla, chain_of_thought, multi_round_feedback)"
    )

    debug_parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model name to use (e.g., gpt-4, gpt-3.5-turbo)"
    )

    debug_parser.add_argument(
        "--trace-output",
        type=str,
        help="Path to save execution trace JSON (optional)"
    )

    debug_parser.add_argument(
        "--dataset",
        type=str,
        default="data/problems.json",
        help="Path to problems dataset (default: data/problems.json)"
    )

    debug_parser.set_defaults(func=run_debug_command)
