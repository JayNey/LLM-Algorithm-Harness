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

        # Initialize strategy with wrapper
        from src.models import StrategyConfig, LLMConfig, SandboxConfig
        from src.llm_client import LLMClient

        # Create configurations
        llm_config = LLMConfig(
            provider="openai",
            api_key="",  # Will use environment variable
            model=args.model,
            temperature=0.7,
            max_tokens=2000,
            timeout=30,
        )

        sandbox_config = SandboxConfig(
            timeout_seconds=5,
            memory_limit_mb=256,
            allowed_imports=["math", "itertools", "collections", "functools", "heapq", "bisect"],
        )

        strategy_config = StrategyConfig(
            name=args.strategy,
            max_iterations=3,
        )

        # Initialize components
        llm_client = LLMClient(llm_config)
        sandbox = SandboxExecutor(sandbox_config)

        # Get strategy class
        from src.harness import AlgorithmHarness
        strategy_class = AlgorithmHarness.STRATEGY_MAP.get(args.strategy)
        if not strategy_class:
            print(f"Error: Unknown strategy '{args.strategy}'")
            print(f"Available strategies: {', '.join(AlgorithmHarness.STRATEGY_MAP.keys())}")
            return 1

        # Create base strategy
        base_strategy = strategy_class(strategy_config, llm_client, sandbox)

        # Wrap with debug strategy - use pause callback to integrate with debugger
        def pause_callback(location: str, context: dict):
            """Called when strategy hits a breakpoint."""
            trace_recorder.record_breakpoint(location, context)
            print(f"\n⊙ Breakpoint hit at '{location}'")
            print(f"Context: {list(context.keys())}")
            # Return to debugger prompt
            debugger.cmdloop()

        wrapped_strategy = DebugStrategyWrapper(
            wrapped_strategy=base_strategy,
            breakpoint_manager=breakpoint_manager,
            pause_callback=pause_callback
        )

        # Give debugger access to strategy and problem
        debugger.strategy = wrapped_strategy
        debugger.problem = problem

        print("Strategy initialized.")
        print("Commands: 'break <location>', 'run', 'next', 'continue', 'trace', 'help'\n")

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
