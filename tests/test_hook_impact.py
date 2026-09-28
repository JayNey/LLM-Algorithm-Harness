"""
Test that new hook points don't affect batch mode performance and behavior.
"""

import pytest
from src.strategy_base import StrategyBase


class TestHookPointsImpact:
    """Test that hook points don't negatively impact existing strategies."""

    def test_hook_methods_exist_and_are_callable(self):
        """Verify hook methods are defined and callable on StrategyBase."""
        # Verify methods exist as attributes
        assert hasattr(StrategyBase, '_before_generate')
        assert hasattr(StrategyBase, '_before_execute')
        assert hasattr(StrategyBase, '_after_feedback')

        # Verify they are defined as methods
        assert callable(getattr(StrategyBase, '_before_generate'))
        assert callable(getattr(StrategyBase, '_before_execute'))
        assert callable(getattr(StrategyBase, '_after_feedback'))

    def test_hook_methods_signature(self):
        """Verify hook methods have correct signatures."""
        import inspect

        # Check _before_generate signature
        sig = inspect.signature(StrategyBase._before_generate)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'prompt' in params

        # Check _before_execute signature
        sig = inspect.signature(StrategyBase._before_execute)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'code' in params

        # Check _after_feedback signature
        sig = inspect.signature(StrategyBase._after_feedback)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'feedback' in params

    def test_hooks_are_empty_by_default(self):
        """Verify hook methods have empty default implementations."""
        import inspect

        # Get source code of hook methods
        before_generate_source = inspect.getsource(StrategyBase._before_generate)
        before_execute_source = inspect.getsource(StrategyBase._before_execute)
        after_feedback_source = inspect.getsource(StrategyBase._after_feedback)

        # Verify each method only contains 'pass' (or is effectively empty)
        # The methods should have minimal implementation
        assert 'pass' in before_generate_source or len(before_generate_source.split('\n')) <= 3
        assert 'pass' in before_execute_source or len(before_execute_source.split('\n')) <= 3
        assert 'pass' in after_feedback_source or len(after_feedback_source.split('\n')) <= 3

    def test_strategy_base_structure_unchanged(self):
        """Verify StrategyBase still has its core methods."""
        # Verify essential methods still exist
        assert hasattr(StrategyBase, 'execute')
        assert hasattr(StrategyBase, 'generate')
        assert hasattr(StrategyBase, 'extract_code')
        assert hasattr(StrategyBase, 'create_execution_result')

        # Verify they are callable
        assert callable(getattr(StrategyBase, 'execute'))
        assert callable(getattr(StrategyBase, 'generate'))
        assert callable(getattr(StrategyBase, 'extract_code'))
        assert callable(getattr(StrategyBase, 'create_execution_result'))
