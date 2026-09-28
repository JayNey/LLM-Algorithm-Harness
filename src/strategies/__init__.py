"""Strategies package."""

from src.strategies.vanilla import VanillaStrategy
from src.strategies.chain_of_thought import ChainOfThoughtStrategy
from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy
from src.strategies.self_consistency import SelfConsistencyStrategy

__all__ = [
    "VanillaStrategy",
    "ChainOfThoughtStrategy",
    "MultiRoundFeedbackStrategy",
    "SelfConsistencyStrategy",
]
