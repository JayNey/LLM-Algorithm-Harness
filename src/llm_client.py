"""
LLM Client - Interface for calling LLM APIs.
"""

import os
import re
import time
from typing import Optional

from pydantic import SecretStr

from src.models import LLMConfig, LLMResponse, TokenUsage
from src.utils.logging import get_logger
from src.utils.secrets import redact_sensitive_text

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

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LLMClient:
    """LLM API client."""

    def __init__(self, config: LLMConfig):
        """
        Initialize LLM client.

        Args:
            config: LLM configuration
        """
        self.config = config
        self._resolved_api_key: Optional[SecretStr] = None
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
            api_key = self._resolve_api_key("OPENAI_API_KEY", "OpenAI")
            self._resolved_api_key = SecretStr(api_key)

            # Support custom base_url for OpenAI-compatible APIs (e.g., DeepSeek)
            client_kwargs = {"api_key": api_key, "max_retries": 3}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
                logger.info(
                    "using_custom_base_url",
                    provider=self.config.provider,
                    base_url=self.config.base_url,
                )

            try:
                return OpenAI(**client_kwargs)
            except Exception as exc:
                raise self._safe_provider_error(exc, api_key) from None

        elif self.config.provider == "anthropic":
            if Anthropic is None:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
            api_key = self._resolve_api_key("ANTHROPIC_API_KEY", "Anthropic")
            self._resolved_api_key = SecretStr(api_key)
            try:
                return Anthropic(api_key=api_key)
            except Exception as exc:
                raise self._safe_provider_error(exc, api_key) from None

        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    def _resolve_api_key(self, default_env: str, provider_name: str) -> str:
        """Resolve a direct key, explicit environment reference, or provider default."""
        configured = (
            self.config.api_key.get_secret_value()
            if isinstance(self.config.api_key, SecretStr)
            else str(self.config.api_key)
        )
        env_name = None

        if configured.startswith("env:"):
            env_name = configured[4:]
        elif configured.startswith("${") and configured.endswith("}"):
            env_name = configured[2:-1]

        if env_name is not None:
            if not _ENV_NAME.fullmatch(env_name):
                raise ValueError("API key environment reference is invalid")
            api_key = os.getenv(env_name)
            if not api_key:
                raise ValueError(f"API key environment variable '{env_name}' is not set")
            return api_key

        if configured:
            return configured

        api_key = os.getenv(default_env)
        if not api_key:
            raise ValueError(
                f"{provider_name} API key not provided; set {default_env} or configure api_key"
            )
        return api_key

    def _safe_provider_error(
        self, error: Exception, resolved_api_key: Optional[str] = None
    ) -> RuntimeError:
        """Create an exception message that cannot contain the resolved credential."""
        api_key = resolved_api_key
        if api_key is None and self._resolved_api_key is not None:
            api_key = self._resolved_api_key.get_secret_value()
        secrets = [api_key] if api_key else []
        return RuntimeError(redact_sensitive_text(str(error), secrets))

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
            safe_error = self._safe_provider_error(e)
            logger.error(
                "llm_api_error", provider=self.config.provider, error=str(safe_error)
            )
            raise safe_error from None

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

        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "timeout": self.config.timeout,
        }

        # Extra provider-specific switches (e.g. SiliconFlow Qwen3.5 thinking mode)
        if self.config.enable_thinking is not None:
            kwargs["extra_body"] = {"enable_thinking": self.config.enable_thinking}

        response = self.client.chat.completions.create(**kwargs)

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
