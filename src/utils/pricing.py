"""
Model pricing management for LLM cost estimation.

This module provides centralized pricing configuration for LLM models,
supporting custom pricing files, built-in defaults, and fallback strategies.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

PricingSource = Literal["custom", "builtin", "default"]


class PricingInfo:
    """Pricing information for a model."""

    def __init__(
        self,
        model: str,
        prompt_price: float,
        completion_price: float,
        source: PricingSource
    ):
        self.model = model
        self.prompt_price = prompt_price
        self.completion_price = completion_price
        self.source = source

    def to_dict(self) -> Dict[str, any]:
        """Convert to dictionary format for serialization."""
        return {
            "model": self.model,
            "prompt_price_per_1k": self.prompt_price,
            "completion_price_per_1k": self.completion_price,
            "source": self.source
        }


class PricingManager:
    """Manages model pricing configuration with fallback strategies."""

    # Built-in pricing dictionary (USD per 1000 tokens)
    BUILTIN_PRICING = {
        "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002},
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "gpt-4o": {"prompt": 0.005, "completion": 0.015},
        "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "claude-3-5-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-5-haiku": {"prompt": 0.001, "completion": 0.005},
    }

    # Default pricing for unknown models
    DEFAULT_PROMPT_PRICE = 0.002
    DEFAULT_COMPLETION_PRICE = 0.002

    def __init__(self, pricing_file: Optional[str] = None):
        """
        Initialize PricingManager.

        Args:
            pricing_file: Path to custom pricing JSON file. If None, looks for
                         'pricing.json' in the current directory.
        """
        self.custom_pricing: Dict[str, Dict[str, float]] = {}
        self.pricing_file = pricing_file or "pricing.json"
        self._load_custom_pricing()

    def _load_custom_pricing(self) -> None:
        """Load custom pricing from JSON file."""
        pricing_path = Path(self.pricing_file)

        if not pricing_path.exists():
            logger.debug(f"Custom pricing file not found: {self.pricing_file}")
            return

        try:
            with open(pricing_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if "models" not in data:
                logger.warning(
                    f"Invalid pricing file format: missing 'models' key in {self.pricing_file}"
                )
                return

            self.custom_pricing = data["models"]
            logger.info(
                f"Loaded custom pricing for {len(self.custom_pricing)} models from {self.pricing_file}"
            )

        except json.JSONDecodeError as e:
            logger.warning(
                f"Failed to parse pricing file {self.pricing_file}: {e}. "
                "Falling back to built-in pricing."
            )
        except Exception as e:
            logger.warning(
                f"Error loading pricing file {self.pricing_file}: {e}. "
                "Falling back to built-in pricing."
            )

    def get_pricing(self, model: str) -> PricingInfo:
        """
        Get pricing information for a model.

        Implements fallback strategy:
        1. Custom pricing (exact match)
        2. Custom pricing (prefix match)
        3. Built-in pricing (exact match)
        4. Built-in pricing (prefix match)
        5. Default pricing with warning

        Args:
            model: Model name (e.g., "gpt-4-0613", "claude-3-opus-20240229")

        Returns:
            PricingInfo object containing pricing and source
        """
        # Try exact match in custom pricing
        if model in self.custom_pricing:
            pricing = self.custom_pricing[model]
            return PricingInfo(
                model=model,
                prompt_price=pricing["prompt"],
                completion_price=pricing["completion"],
                source="custom"
            )

        # Try prefix match in custom pricing
        for key in self.custom_pricing:
            if model.startswith(key):
                pricing = self.custom_pricing[key]
                logger.debug(f"Prefix match: {model} matched to custom pricing key '{key}'")
                return PricingInfo(
                    model=model,
                    prompt_price=pricing["prompt"],
                    completion_price=pricing["completion"],
                    source="custom"
                )

        # Try exact match in built-in pricing
        if model in self.BUILTIN_PRICING:
            pricing = self.BUILTIN_PRICING[model]
            return PricingInfo(
                model=model,
                prompt_price=pricing["prompt"],
                completion_price=pricing["completion"],
                source="builtin"
            )

        # Try prefix match in built-in pricing
        for key in self.BUILTIN_PRICING:
            if model.startswith(key):
                pricing = self.BUILTIN_PRICING[key]
                logger.debug(f"Prefix match: {model} matched to built-in pricing key '{key}'")
                return PricingInfo(
                    model=model,
                    prompt_price=pricing["prompt"],
                    completion_price=pricing["completion"],
                    source="builtin"
                )

        # Fall back to default pricing with warning
        logger.warning(
            f"Unknown model '{model}' - using default pricing "
            f"(prompt: ${self.DEFAULT_PROMPT_PRICE}/1k, "
            f"completion: ${self.DEFAULT_COMPLETION_PRICE}/1k). "
            f"Consider adding this model to {self.pricing_file}"
        )
        return PricingInfo(
            model=model,
            prompt_price=self.DEFAULT_PROMPT_PRICE,
            completion_price=self.DEFAULT_COMPLETION_PRICE,
            source="default"
        )

    def load_custom_pricing(self, pricing_file: str) -> None:
        """
        Load or reload custom pricing from a different file.

        Args:
            pricing_file: Path to pricing JSON file
        """
        self.pricing_file = pricing_file
        self.custom_pricing = {}
        self._load_custom_pricing()

    def __repr__(self) -> str:
        return (
            f"PricingManager(custom_models={len(self.custom_pricing)}, "
            f"builtin_models={len(self.BUILTIN_PRICING)})"
        )
