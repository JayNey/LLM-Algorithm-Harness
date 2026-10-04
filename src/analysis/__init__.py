"""
Code evolution analysis module.

This module provides tools for analyzing code quality evolution across
multi-round iteration strategies.
"""

from typing import Any

__all__ = ["EvolutionAnalyzer"]


def __getattr__(name: str) -> Any:
    """Lazy import for EvolutionAnalyzer."""
    if name == "EvolutionAnalyzer":
        from src.analysis.evolution import EvolutionAnalyzer

        return EvolutionAnalyzer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
