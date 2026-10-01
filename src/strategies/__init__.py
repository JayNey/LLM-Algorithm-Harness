"""Strategies package."""

from src.strategies.chain_of_thought import ChainOfThoughtStrategy
from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy
from src.strategies.reflexion import ReflexionStrategy
from src.strategies.self_consistency import SelfConsistencyStrategy
from src.strategies.vanilla import VanillaStrategy

__all__ = [
    "VanillaStrategy",
    "ChainOfThoughtStrategy",
    "MultiRoundFeedbackStrategy",
    "ReflexionStrategy",
    "SelfConsistencyStrategy",
]
