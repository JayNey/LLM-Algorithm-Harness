"""
Strategy wrapper for interactive debugging.
"""

from typing import Optional, Callable
from src.strategy_base import StrategyBase
from src.models import Problem, ExecutionResult
from harness.debug.breakpoint import BreakpointManager


class DebugStrategyWrapper(StrategyBase):
    """
    Wrapper that adds debugging capabilities to an existing strategy.

    Uses decorator pattern to intercept hook points and pause execution
    when breakpoints are hit.
    """

    def __init__(
        self,
        wrapped_strategy: StrategyBase,
        breakpoint_manager: BreakpointManager,
        pause_callback: Optional[Callable[[str, dict], None]] = None,
    ):
        """
        Initialize debug wrapper.

        Args:
            wrapped_strategy: The strategy to wrap
            breakpoint_manager: Breakpoint manager instance
            pause_callback: Callback function to invoke when paused
                           Called with (location, context_data)
        """
        # Initialize parent with wrapped strategy's components
        super().__init__(
            wrapped_strategy.config,
            wrapped_strategy.llm_client,
            wrapped_strategy.sandbox,
        )
        self._wrapped = wrapped_strategy
        self._breakpoint_manager = breakpoint_manager
        self._pause_callback = pause_callback
        self._paused = False
        self._skip_next = False

    def _before_generate(self, prompt: str) -> None:
        """Hook before generating code."""
        if self._breakpoint_manager.should_break("generate") and not self._skip_next:
            self._pause_at("generate", {"prompt": prompt})
        self._skip_next = False

    def _before_execute(self, code: str) -> None:
        """Hook before executing code."""
        if self._breakpoint_manager.should_break("execute") and not self._skip_next:
            self._pause_at("execute", {"code": code})
        self._skip_next = False

    def _after_feedback(self, feedback: str) -> None:
        """Hook after receiving feedback."""
        if self._breakpoint_manager.should_break("feedback") and not self._skip_next:
            self._pause_at("feedback", {"feedback": feedback})
        self._skip_next = False

    def _pause_at(self, location: str, context: dict) -> None:
        """
        Pause execution at a breakpoint.

        Args:
            location: Breakpoint location name
            context: Context data at this point
        """
        self._paused = True
        if self._pause_callback:
            self._pause_callback(location, context)

    def skip_next_breakpoint(self) -> None:
        """Skip the next breakpoint that would be hit."""
        self._skip_next = True

    def is_paused(self) -> bool:
        """Check if currently paused."""
        return self._paused

    def resume(self) -> None:
        """Resume execution from pause."""
        self._paused = False

    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute wrapped strategy with debugging support.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult from wrapped strategy
        """
        # Delegate to wrapped strategy
        return self._wrapped.execute(problem)

    def __getattr__(self, name: str):
        """
        Delegate attribute access to wrapped strategy.

        This allows the wrapper to be transparent for methods
        not explicitly overridden.
        """
        return getattr(self._wrapped, name)
