"""
LLM Client - Interface for calling LLM APIs.
"""

import os
import time
from typing import Optional

from src.models import LLMConfig, LLMResponse, TokenUsage
from src.utils.logging import get_logger
from src.utils.pricing import PricingManager

# Optional imports for LLM providers (may not be installed)
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

logger = get_logger(__name__)


class LLMClient:
    """LLM API client."""

    def __init__(self, config: LLMConfig):
        """
        Initialize LLM client.

        Args:
            config: LLM configuration
        """
        self.config = config
        self.client = self._initialize_client()
        self.pricing_manager = PricingManager()
        logger.info("llm_client_initialized", provider=config.provider, model=config.model)

    def _initialize_client(self):
        """
        Initialize provider-specific client.

        Returns:
            Initialized client

        Raises:
            ValueError: If provider not supported
        """
        if self.config.provider == "openai":
            if OpenAI is None:
                raise ImportError("openai package not installed. Run: pip install openai")
            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not provided")

            # Support custom base_url for OpenAI-compatible APIs (e.g., DeepSeek)
            client_kwargs = {"api_key": api_key}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
                logger.info(
                    "using_custom_base_url",
                    provider=self.config.provider,
                    base_url=self.config.base_url,
                )

            return OpenAI(**client_kwargs)

        elif self.config.provider == "anthropic":
            if Anthropic is None:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
            api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("Anthropic API key not provided")
            return Anthropic(api_key=api_key)

        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> LLMResponse:
        """
        Generate response from LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse object

        Raises:
            Exception: If API call fails
        """
        logger.info("generating_llm_response", provider=self.config.provider, model=self.config.model)

        start_time = time.time()

        try:
            if self.config.provider == "openai":
                response = self._call_openai(prompt, system_prompt)
            elif self.config.provider == "anthropic":
                response = self._call_anthropic(prompt, system_prompt)
            else:
                raise ValueError(f"Unsupported provider: {self.config.provider}")

            response_time = time.time() - start_time

            logger.info(
                "llm_response_received",
                provider=self.config.provider,
                model=self.config.model,
                tokens=response.usage.total_tokens,
                time=response_time,
            )

            return response

        except Exception as e:
            logger.error("llm_api_error", provider=self.config.provider, error=str(e))
            raise

    def _call_openai(self, prompt: str, system_prompt: Optional[str]) -> LLMResponse:
        """
        Call OpenAI API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout,
        )

        # Get pricing metadata for this model
        pricing_info = self.pricing_manager.get_pricing(response.model)

        return LLMResponse(
            text=response.choices[0].message.content,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
            model=response.model,
            finish_reason=response.choices[0].finish_reason,
            pricing_metadata={
                "model": response.model,
                "prompt_price_per_1k": pricing_info.prompt_price,
                "completion_price_per_1k": pricing_info.completion_price,
                "source": pricing_info.source,
            },
        )

    def _call_anthropic(self, prompt: str, system_prompt: Optional[str]) -> LLMResponse:
        """
        Call Anthropic API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse
        """
        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)

        # Get pricing metadata for this model
        pricing_info = self.pricing_manager.get_pricing(response.model)

        return LLMResponse(
            text=response.content[0].text,
            usage=TokenUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            ),
            model=response.model,
            finish_reason=response.stop_reason,
            pricing_metadata={
                "model": response.model,
                "prompt_price_per_1k": pricing_info.prompt_price,
                "completion_price_per_1k": pricing_info.completion_price,
                "source": pricing_info.source,
            },
        )

    def estimate_cost(self, usage: TokenUsage) -> float:
        """
        Estimate API call cost.

        Args:
            usage: Token usage

        Returns:
            Estimated cost in USD
        """
        pricing_info = self.pricing_manager.get_pricing(self.config.model)

        if pricing_info.source == "default":
            logger.warning(
                "unknown_model_pricing",
                model=self.config.model,
                using_default_pricing=f"${pricing_info.prompt_price}/{pricing_info.completion_price} per 1K tokens"
            )

        cost = (
            usage.prompt_tokens * pricing_info.prompt_price / 1000
            + usage.completion_tokens * pricing_info.completion_price / 1000
        )

        return cost

        return cost
