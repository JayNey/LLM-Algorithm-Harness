"""
Strategy wrapper for interactive debugging.
"""

from collections.abc import Callable
from functools import partial
from typing import Any

from harness.debug.breakpoint import BreakpointManager
from harness.debug.debugger import Debugger, DebugSessionExit
from src.models import ExecutionResult, LLMResponse, Problem, SandboxResult
from src.strategy_base import StrategyBase


class _DebugDependency:
    """Override one operation while delegating the dependency's other attributes."""

    def __init__(self, dependency: Any, **operations: Callable):
        self._dependency = dependency
        vars(self).update(operations)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._dependency, name)


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
        pause_callback: Callable[[str, dict], None] | None = None,
        *,
        debugger: Debugger | None = None,
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
        self._debugger = debugger
        self._breakpoint_manager = breakpoint_manager
        self._pause_callback = pause_callback
        self._paused = False
        self._skip_next = False

        if debugger is None:
            wrapped_strategy._before_generate = self._before_generate  # type: ignore[method-assign]
            wrapped_strategy._before_execute = self._before_execute  # type: ignore[method-assign]
            wrapped_strategy._after_feedback = self._after_feedback  # type: ignore[method-assign]

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

    def _generate(self, prompt: str, *, round_limit: int | None, **kwargs: Any) -> LLMResponse:
        debugger = self._debugger
        assert debugger is not None
        trace = debugger.trace_recorder
        trace.complete_round()

        edited, injected = debugger.modified_prompt, debugger.injected_text
        debugger.modified_prompt = debugger.injected_text = None
        if edited is not None:
            prompt = edited
        if injected:
            prompt = f"{prompt}\n\n{injected}"
            print(f"\nNext prompt:\n{trace.redact(prompt)}")
        debugger.current_prompt = prompt
        trace.start_round(trace.get_round_count() + 1, prompt)
        if edited is not None:
            trace.record_intervention("edit_prompt", edited)
        if injected:
            trace.record_intervention("inject", injected)
        if round_limit is not None:
            trace.record_intervention("set_parameter", f"max_rounds = {round_limit}")
        for parameter in ("temperature", "max_tokens"):
            if parameter in debugger.param_overrides:
                value = debugger.param_overrides[parameter]
                kwargs[parameter] = value
                custom_params = kwargs.get("custom_params")
                if custom_params and parameter in custom_params:
                    kwargs["custom_params"] = {**custom_params, parameter: value}
                trace.record_intervention("set_parameter", f"{parameter} = {value}")

        try:
            response = self.llm_client.generate(prompt, **kwargs)
        except Exception as exc:
            trace.update_status("error")
            trace.record_feedback(str(exc))
            raise
        trace.record_response(response.text)
        trace.update_status("generated")
        if debugger.pause("generate", response.text):
            trace.update_status("skipped")
            return response.model_copy(update={"text": ""})
        return response

    def _execute_code(self, code: str, problem: Problem, **kwargs: Any) -> SandboxResult:
        debugger = self._debugger
        assert debugger is not None
        trace = debugger.trace_recorder
        trace.record_code(code)
        if debugger.pause("execute", code):
            trace.update_status("skipped")
            return SandboxResult(status="failed", error_message="Sandbox execution skipped")
        try:
            result = self.sandbox.execute(code, problem, **kwargs)
        except Exception as exc:
            trace.update_status("error")
            trace.record_feedback(str(exc))
            debugger.pause("feedback", str(exc))
            raise
        trace.record_execution(
            {**result.model_dump(mode="json"), "stage": kwargs.get("stage", "public")}
        )
        trace.update_status("passed" if result.all_passed else "failed")
        feedback = f"All passed: {result.all_passed}, Status: {result.status}"
        if result.error_message:
            feedback += f"\n{result.error_message}"
        trace.record_feedback(feedback)
        debugger.pause("feedback", feedback)
        return result

    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute wrapped strategy with debugging support.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult from wrapped strategy
        """
        if self._debugger is None:
            return self._wrapped.execute(problem)

        trace = self._debugger.trace_recorder
        configured_rounds = self.config.max_iterations
        round_limit = self._debugger.param_overrides.get("max_rounds")
        if round_limit is not None:
            self.config.max_iterations = round_limit
        self._wrapped.llm_client = _DebugDependency(  # type: ignore[assignment]
            self.llm_client, generate=partial(self._generate, round_limit=round_limit)
        )
        self._wrapped.sandbox = _DebugDependency(  # type: ignore[assignment]
            self.sandbox, execute=self._execute_code
        )
        try:
            return self._wrapped.execute(problem)
        except DebugSessionExit:
            trace.update_status("cancelled")
            raise
        except Exception:
            trace.update_status("error")
            raise
        finally:
            trace.complete_round()
            self.config.max_iterations = configured_rounds
            self._wrapped.llm_client = self.llm_client
            self._wrapped.sandbox = self.sandbox

    def __getattr__(self, name: str) -> Any:
        """
        Delegate attribute access to wrapped strategy.

        This allows the wrapper to be transparent for methods
        not explicitly overridden.
        """
        return getattr(self._wrapped, name)
