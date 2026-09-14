"""
LLM Client - Interface for calling LLM APIs.
"""

import os
import time
from typing import Optional

from src.models import LLMConfig, LLMResponse, TokenUsage
from src.utils.logging import get_logger

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
            return OpenAI(api_key=api_key)

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

        return LLMResponse(
            text=response.choices[0].message.content,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
            model=response.model,
            finish_reason=response.choices[0].finish_reason,
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

        return LLMResponse(
            text=response.content[0].text,
            usage=TokenUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            ),
            model=response.model,
            finish_reason=response.stop_reason,
        )

    def estimate_cost(self, usage: TokenUsage) -> float:
        """
        Estimate API call cost.

        Args:
            usage: Token usage

        Returns:
            Estimated cost in USD
        """
        # Pricing (as of 2024, approximate)
        pricing = {
            "gpt-3.5-turbo": {"prompt": 0.0015 / 1000, "completion": 0.002 / 1000},
            "gpt-4": {"prompt": 0.03 / 1000, "completion": 0.06 / 1000},
            "gpt-4-turbo": {"prompt": 0.01 / 1000, "completion": 0.03 / 1000},
            "claude-3-haiku": {"prompt": 0.00025 / 1000, "completion": 0.00125 / 1000},
            "claude-3-sonnet": {"prompt": 0.003 / 1000, "completion": 0.015 / 1000},
            "claude-3-opus": {"prompt": 0.015 / 1000, "completion": 0.075 / 1000},
        }

        model_pricing = pricing.get(self.config.model)
        if not model_pricing:
            logger.warning("unknown_model_pricing", model=self.config.model)
            return 0.0

        cost = (
            usage.prompt_tokens * model_pricing["prompt"]
            + usage.completion_tokens * model_pricing["completion"]
        )

        return cost
