"""
Model pricing management for LLM cost estimation.

This module provides centralized pricing configuration for LLM models,
supporting custom pricing files and built-in pricing. Models without any
configurable pricing are marked "unknown" instead of being converted with a
fabricated default, so reports never show a confident $0-style estimate for
an unpriced model (issue #15).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)

PricingSource = Literal["custom", "builtin", "unknown"]


class PricingInfo:
    """Pricing information for a model."""

    def __init__(
        self,
        model: str,
        prompt_price: Optional[float],
        completion_price: Optional[float],
        source: PricingSource,
        as_of: Optional[str] = None,
    ):
        self.model = model
        self.prompt_price = prompt_price
        self.completion_price = completion_price
        self.source = source
        self.as_of = as_of

    @property
    def pricing_known(self) -> bool:
        """Whether both unit prices are actually configured."""
        return self.prompt_price is not None and self.completion_price is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for serialization."""
        return {
            "model": self.model,
            "prompt_price_per_1k": self.prompt_price,
            "completion_price_per_1k": self.completion_price,
            "source": self.source,
            "as_of": self.as_of,
            "pricing_known": self.pricing_known,
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

    def __init__(self, pricing_file: Optional[str] = None):
        """
        Initialize PricingManager.

        Args:
            pricing_file: Path to custom pricing JSON file. If None, looks for
                         'pricing.json' in the current directory.
        """
        self.custom_pricing: Dict[str, Dict[str, Any]] = {}
        self.pricing_file = pricing_file or "pricing.json"
        self._load_custom_pricing()

    def _load_custom_pricing(self) -> None:
        """Load custom pricing from JSON file."""
        pricing_path = Path(self.pricing_file)

        if not pricing_path.exists():
            logger.debug(f"Custom pricing file not found: {self.pricing_file}")
            return

        try:
            with open(pricing_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "models" not in data:
                logger.warning(
                    f"Invalid pricing file format: missing 'models' key in {self.pricing_file}"
                )
                return

            normalized: Dict[str, Dict[str, Any]] = {}
            for model_key, raw in data["models"].items():
                entry = self._normalize_entry(raw)
                if entry is None:
                    logger.warning(
                        f"Skipping pricing entry '{model_key}' in {self.pricing_file}: "
                        "missing prompt/completion prices"
                    )
                    continue
                normalized[model_key] = entry

            self.custom_pricing = normalized
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

    @staticmethod
    def _normalize_entry(raw: Any) -> Optional[Dict[str, Any]]:
        """Accept both short and long price keys plus an optional as_of date."""
        if not isinstance(raw, dict):
            return None
        prompt = raw.get("prompt", raw.get("prompt_price_per_1k"))
        completion = raw.get("completion", raw.get("completion_price_per_1k"))
        if not isinstance(prompt, (int, float)) or not isinstance(completion, (int, float)):
            return None
        as_of = raw.get("as_of")
        entry: Dict[str, Any] = {"prompt": prompt, "completion": completion}
        if isinstance(as_of, str) and as_of.strip():
            entry["as_of"] = as_of.strip()
        return entry

    def get_pricing(self, model: str) -> PricingInfo:
        """
        Get pricing information for a model.

        Implements fallback strategy:
        1. Custom pricing (exact match)
        2. Custom pricing (prefix match)
        3. Built-in pricing (exact match)
        4. Built-in pricing (prefix match)
        5. Explicit "unknown" marking - never a fabricated default price

        Args:
            model: Model name (e.g., "gpt-4-0613", "claude-3-opus-20240229")

        Returns:
            PricingInfo object containing pricing, source, and as_of date
        """
        # Try exact match in custom pricing
        if model in self.custom_pricing:
            return self._pricing_from_entry(model, self.custom_pricing[model], "custom")

        # Try prefix match in custom pricing (longest match first)
        for key in sorted(self.custom_pricing.keys(), key=len, reverse=True):
            if model.startswith(key):
                logger.debug(f"Prefix match: {model} matched to custom pricing key '{key}'")
                return self._pricing_from_entry(model, self.custom_pricing[key], "custom")

        # Try exact match in built-in pricing
        if model in self.BUILTIN_PRICING:
            return self._pricing_from_entry(model, self.BUILTIN_PRICING[model], "builtin")

        # Try prefix match in built-in pricing
        for key in self.BUILTIN_PRICING:
            if model.startswith(key):
                logger.debug(f"Prefix match: {model} matched to built-in pricing key '{key}'")
                return self._pricing_from_entry(model, self.BUILTIN_PRICING[key], "builtin")

        # Unknown pricing: mark explicitly instead of estimating with defaults
        logger.warning(
            f"Unknown model '{model}' - no pricing configured; cost will be "
            f"reported as unknown. Consider adding this model to {self.pricing_file}"
        )
        return PricingInfo(model=model, prompt_price=None, completion_price=None, source="unknown")

    @classmethod
    def _pricing_from_entry(
        cls, model: str, entry: Dict[str, Any], source: PricingSource
    ) -> PricingInfo:
        return PricingInfo(
            model=model,
            prompt_price=entry["prompt"],
            completion_price=entry["completion"],
            source=source,
            as_of=entry.get("as_of"),
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
