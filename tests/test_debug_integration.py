"""
Integration tests for interactive debugging hooks.

These tests verify that the hook methods (_before_generate, _before_execute,
_after_feedback) are actually called during strategy execution.
"""

import pytest
from unittest.mock import Mock, patch, call

from src.strategies.vanilla import VanillaStrategy
from src.strategies.chain_of_thought import ChainOfThoughtStrategy
from harness.debug.strategy_wrapper import DebugStrategyWrapper
from harness.debug.breakpoint import BreakpointManager

# Import to resolve forward references
from src.code_quality.models import CodeQualityMetrics  # noqa: F401
from src.models import ExecutionResult
ExecutionResult.model_rebuild()


def test_vanilla_strategy_calls_hooks(
    sample_problem,
    sample_strategy_config,
    mock_llm_client,
    mock_sandbox_executor
):
    """Test that VanillaStrategy calls all three hook methods."""
    # Create strategy with mocked dependencies
    strategy = VanillaStrategy(
        config=sample_strategy_config,
        llm_client=mock_llm_client,
        sandbox=mock_sandbox_executor
    )

    # Spy on the hook methods
    with patch.object(strategy, '_before_generate', wraps=strategy._before_generate) as mock_before_gen, \
         patch.object(strategy, '_before_execute', wraps=strategy._before_execute) as mock_before_exec, \
         patch.object(strategy, '_after_feedback', wraps=strategy._after_feedback) as mock_after_fb:

        # Execute the strategy
        result = strategy.execute(sample_problem)

        # Verify hooks were called
        assert mock_before_gen.call_count >= 1, "generate hook should be called at least once"
        assert mock_before_exec.call_count >= 1, "execute hook should be called at least once"
        assert mock_after_fb.call_count >= 1, "feedback hook should be called at least once"

        # Verify execution succeeded
        assert result is not None


def test_chain_of_thought_strategy_calls_hooks(
    sample_problem,
    sample_strategy_config,
    mock_llm_client,
    mock_sandbox_executor
):
    """Test that ChainOfThoughtStrategy calls all three hook methods."""
    # Create strategy with mocked dependencies
    strategy = ChainOfThoughtStrategy(
        config=sample_strategy_config,
        llm_client=mock_llm_client,
        sandbox=mock_sandbox_executor
    )

    # Spy on the hook methods
    with patch.object(strategy, '_before_generate', wraps=strategy._before_generate) as mock_before_gen, \
         patch.object(strategy, '_before_execute', wraps=strategy._before_execute) as mock_before_exec, \
         patch.object(strategy, '_after_feedback', wraps=strategy._after_feedback) as mock_after_fb:

        # Execute the strategy
        result = strategy.execute(sample_problem)

        # Verify hooks were called
        assert mock_before_gen.call_count >= 1, "generate hook should be called"
        assert mock_before_exec.call_count >= 1, "execute hook should be called"
        assert mock_after_fb.call_count >= 1, "feedback hook should be called"

        # Verify execution succeeded
        assert result is not None


def test_debug_wrapper_intercepts_hooks(
    sample_problem,
    sample_strategy_config,
    mock_llm_client,
    mock_sandbox_executor
):
    """Test that DebugStrategyWrapper intercepts hook calls."""
    # Create base strategy
    base_strategy = VanillaStrategy(
        config=sample_strategy_config,
        llm_client=mock_llm_client,
        sandbox=mock_sandbox_executor
    )

    # Create debug wrapper
    breakpoint_manager = BreakpointManager()
    wrapped_strategy = DebugStrategyWrapper(base_strategy, breakpoint_manager)

    # Spy on the wrapped strategy's hooks (which now point to wrapper's methods)
    # These are the actual methods that will be called during execution
    with patch.object(base_strategy, '_before_generate', wraps=base_strategy._before_generate) as mock_gen, \
         patch.object(base_strategy, '_before_execute', wraps=base_strategy._before_execute) as mock_exec, \
         patch.object(base_strategy, '_after_feedback', wraps=base_strategy._after_feedback) as mock_fb:

        # Execute through wrapper
        result = wrapped_strategy.execute(sample_problem)

        # Verify wrapper hooks were called via the wrapped strategy
        assert mock_gen.call_count >= 1, "wrapper generate hook should intercept calls"
        assert mock_exec.call_count >= 1, "wrapper execute hook should intercept calls"
        assert mock_fb.call_count >= 1, "wrapper feedback hook should intercept calls"

        # Verify execution succeeded
        assert result is not None


def test_hook_arguments_are_passed_correctly(
    sample_problem,
    sample_strategy_config,
    mock_llm_client,
    mock_sandbox_executor
):
    """Test that hook methods receive correct arguments."""
    strategy = VanillaStrategy(
        config=sample_strategy_config,
        llm_client=mock_llm_client,
        sandbox=mock_sandbox_executor
    )

    captured_args = {
        'generate': [],
        'execute': [],
        'feedback': []
    }

    # Wrap hooks to capture arguments
    original_before_gen = strategy._before_generate
    original_before_exec = strategy._before_execute
    original_after_fb = strategy._after_feedback

    def capture_gen(prompt):
        captured_args['generate'].append(prompt)
        return original_before_gen(prompt)

    def capture_exec(code):
        captured_args['execute'].append(code)
        return original_before_exec(code)

    def capture_fb(feedback):
        captured_args['feedback'].append(feedback)
        return original_after_fb(feedback)

    strategy._before_generate = capture_gen
    strategy._before_execute = capture_exec
    strategy._after_feedback = capture_fb

    # Execute
    result = strategy.execute(sample_problem)

    # Verify arguments were captured
    assert len(captured_args['generate']) > 0, "generate hook should receive prompts"
    assert len(captured_args['execute']) > 0, "execute hook should receive code"
    assert len(captured_args['feedback']) > 0, "feedback hook should receive feedback"

    # Verify argument types
    assert all(isinstance(p, str) for p in captured_args['generate']), "prompts should be strings"
    assert all(isinstance(c, str) for c in captured_args['execute']), "code should be strings"
    # feedback can be various types (str, dict, SandboxResult, etc.)


def test_hooks_called_in_correct_order(
    sample_problem,
    sample_strategy_config,
    mock_llm_client,
    mock_sandbox_executor
):
    """Test that hooks are called in the correct sequence."""
    strategy = VanillaStrategy(
        config=sample_strategy_config,
        llm_client=mock_llm_client,
        sandbox=mock_sandbox_executor
    )

    call_sequence = []

    # Wrap hooks to track call order
    original_before_gen = strategy._before_generate
    original_before_exec = strategy._before_execute
    original_after_fb = strategy._after_feedback

    def track_gen(prompt):
        call_sequence.append('generate')
        return original_before_gen(prompt)

    def track_exec(code):
        call_sequence.append('execute')
        return original_before_exec(code)

    def track_fb(feedback):
        call_sequence.append('feedback')
        return original_after_fb(feedback)

    strategy._before_generate = track_gen
    strategy._before_execute = track_exec
    strategy._after_feedback = track_fb

    # Execute
    result = strategy.execute(sample_problem)

    # Verify sequence: should be generate -> execute -> feedback (at least once)
    assert 'generate' in call_sequence, "generate should be called"
    assert 'execute' in call_sequence, "execute should be called"
    assert 'feedback' in call_sequence, "feedback should be called"

    # Verify generate comes before execute
    gen_idx = call_sequence.index('generate')
    exec_idx = call_sequence.index('execute')
    assert gen_idx < exec_idx, "generate should come before execute"

    # Verify execute comes before feedback
    assert exec_idx < call_sequence.index('feedback'), "execute should come before feedback"
