"""
LLM Client - Interface for calling LLM APIs.
"""

import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

from pydantic import SecretStr

from src.models import LLMConfig, LLMResponse, TokenUsage
from src.utils.logging import get_logger
from src.utils.pricing import PricingManager
from src.utils.secrets import redact_sensitive_data, redact_sensitive_text

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
        if self.config.provider in ("openai", "local"):
            if OpenAI is None:
                raise ImportError("openai package not installed. Run: pip install openai")
            if self.config.provider == "local" and not self.config.base_url:
                raise ValueError(
                    "provider=local requires base_url for its OpenAI-compatible endpoint"
                )
            api_key = self._resolve_api_key(
                "OPENAI_API_KEY", "OpenAI", allow_missing=self.config.provider == "local"
            )
            self._resolved_api_key = SecretStr(api_key)

            # Support custom base_url for OpenAI-compatible APIs (e.g., DeepSeek)
            # Keep retries in one place (_call_with_retry) to avoid SDK retry
            # multiplication when a provider returns a rate-limit/5xx error.
            client_kwargs = {"api_key": api_key, "max_retries": 0}
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

        elif self.config.provider == "siliconflow":
            # SiliconFlow exposes an OpenAI-compatible API; reuse the SDK and
            # only inject the service preset (base_url + dedicated key source)
            if OpenAI is None:
                raise ImportError("openai package not installed. Run: pip install openai")
            api_key = self._resolve_api_key("SILICONFLOW_API_KEY", "SiliconFlow")
            self._resolved_api_key = SecretStr(api_key)

            client_kwargs = {"api_key": api_key, "max_retries": 0}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
                logger.info(
                    "using_custom_base_url",
                    provider=self.config.provider,
                    base_url=self.config.base_url,
                )
            else:
                client_kwargs["base_url"] = "https://api.siliconflow.cn/v1"
                logger.info(
                    "using_preset_base_url",
                    provider=self.config.provider,
                    base_url=client_kwargs["base_url"],
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
                # Timeout is also passed to messages.create so it applies to
                # each request even when the SDK constructor is mocked.
                return Anthropic(api_key=api_key, max_retries=0)
            except Exception as exc:
                raise self._safe_provider_error(exc, api_key) from None

        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    def _resolve_api_key(
        self, default_env: str, provider_name: str, *, allow_missing: bool = False
    ) -> str:
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
        if not api_key and allow_missing:
            # Local OpenAI-compatible servers commonly do not authenticate;
            # the SDK still requires a non-empty value in its constructor.
            return "local"
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

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        custom_params: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
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
        effective = self._effective_params(
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            custom_params=custom_params,
        )
        logger.info(
            "generating_llm_response", provider=self.config.provider, model=self.config.model
        )

        start_time = time.time()

        try:
            if self.config.provider in ("openai", "local", "siliconflow"):
                response = self._call_openai(prompt, effective)
            elif self.config.provider == "anthropic":
                response = self._call_anthropic(prompt, effective)
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
            logger.error("llm_api_error", provider=self.config.provider, error=str(safe_error))
            raise safe_error from None

    def _effective_params(
        self,
        *,
        system_prompt: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        custom_params: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Resolve strategy overrides against the global LLM configuration."""
        params: Dict[str, Any] = {
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "timeout": self.config.timeout,
            "system_prompt": system_prompt,
        }
        if self.config.enable_thinking is not None:
            params["enable_thinking"] = self.config.enable_thinking
        if custom_params:
            # Strategy-specific values intentionally override global extras,
            # while reserved request fields remain controlled by this method.
            for key, value in custom_params.items():
                if key not in {"model", "messages", "timeout", "system_prompt"}:
                    params[key] = value
        return params

    @staticmethod
    def _extract_text(content: Any) -> str:
        """Normalize string and provider content blocks into answer text."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            value = content.get("text")
            if value is None:
                value = (
                    content.get("thinking") or content.get("reasoning") or content.get("content")
                )
            return value if isinstance(value, str) else ""
        if isinstance(content, (list, tuple)):
            parts = []
            for part in content:
                block_type = (
                    part.get("type") if isinstance(part, dict) else getattr(part, "type", None)
                )
                if block_type in {"thinking", "reasoning"}:
                    continue
                parts.append(LLMClient._extract_text(part))
            return "".join(part for part in parts if part)
        value = getattr(content, "text", None)
        if value is None:
            value = getattr(content, "thinking", None) or getattr(content, "reasoning", None)
        return value if isinstance(value, str) else ""

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        """Read a field from either an SDK object or a dict fixture."""
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @staticmethod
    def _extract_reasoning(message: Any) -> Optional[str]:
        """Read optional reasoning fields without mixing them into code text."""
        for key in ("reasoning_content", "reasoning", "thinking"):
            value = message.get(key) if isinstance(message, dict) else getattr(message, key, None)
            text = LLMClient._extract_text(value)
            if text:
                return text
        content = (
            message.get("content")
            if isinstance(message, dict)
            else getattr(message, "content", None)
        )
        if isinstance(content, (list, tuple)):
            parts = []
            for block in content:
                block_type = (
                    block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                )
                if block_type in {"thinking", "reasoning"}:
                    parts.append(LLMClient._extract_text(block))
            combined = "".join(parts)
            return combined or None
        return None

    @staticmethod
    def _status_code(error: Exception) -> Optional[int]:
        """Extract HTTP status from SDK errors without importing SDK classes."""
        for candidate in (error, getattr(error, "response", None)):
            value = getattr(candidate, "status_code", None)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
        return None

    @classmethod
    def _is_retryable_error(cls, error: Exception) -> bool:
        status = cls._status_code(error)
        if (
            status == 401
            or status == 403
            or (status is not None and 400 <= status < 500 and status != 429)
        ):
            return False
        if status == 429 or (status is not None and status >= 500):
            return True
        name = error.__class__.__name__.lower()
        return any(
            token in name for token in ("ratelimit", "timeout", "connection", "internalserver")
        )

    def _call_with_retry(self, operation: Callable[[], Any]) -> Any:
        """Run one provider operation with bounded retry and backoff."""
        started = time.monotonic()
        last_error: Optional[Exception] = None
        for attempt in range(self.config.retry_max_attempts):
            try:
                return operation()
            except Exception as error:
                last_error = error
                if (
                    not self._is_retryable_error(error)
                    or attempt + 1 >= self.config.retry_max_attempts
                ):
                    raise
                delay = self.config.retry_backoff_seconds * (2**attempt)
                elapsed = time.monotonic() - started
                if self.config.retry_max_elapsed_seconds <= elapsed + delay:
                    raise
                if delay:
                    time.sleep(delay)
        assert last_error is not None
        raise last_error

    def _call_openai(self, prompt: str, effective: Dict[str, Any]) -> LLMResponse:
        """
        Call OpenAI API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            LLMResponse
        """
        messages = []
        if effective.get("system_prompt"):
            messages.append({"role": "system", "content": effective["system_prompt"]})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": effective["temperature"],
            "max_tokens": effective["max_tokens"],
            "timeout": effective["timeout"],
        }

        # Provider-specific switches can be supplied through custom_params.
        extra_body = effective.get("extra_body")
        if effective.get("enable_thinking") is not None:
            extra_body = {**(extra_body or {}), "enable_thinking": effective["enable_thinking"]}
        if extra_body:
            kwargs["extra_body"] = extra_body
        for key, value in effective.items():
            if key not in {
                "system_prompt",
                "temperature",
                "max_tokens",
                "timeout",
                "enable_thinking",
                "extra_body",
            }:
                kwargs[key] = value

        response = self._call_with_retry(lambda: self.client.chat.completions.create(**kwargs))

        token_usage, usage_missing = self._openai_usage(self._field(response, "usage"))

        # Get pricing metadata for this model
        model = self._field(response, "model") or self.config.model
        pricing_info = self.pricing_manager.get_pricing(model)
        choices = self._field(response, "choices")
        choice = choices[0] if choices else None
        message = self._field(choice, "message") if choice is not None else None
        usage_metadata = {
            "usage_known": not usage_missing,
            "total_cost": (
                (
                    token_usage.prompt_tokens * pricing_info.prompt_price / 1000
                    + token_usage.completion_tokens * pricing_info.completion_price / 1000
                )
                if not usage_missing
                else None
            ),
        }

        return LLMResponse(
            text=self._extract_text(
                self._field(message, "content") if message is not None else None
            ),
            usage=token_usage,
            model=model,
            finish_reason=self._field(choice, "finish_reason"),
            pricing_metadata={
                "model": model,
                "prompt_price_per_1k": pricing_info.prompt_price,
                "completion_price_per_1k": pricing_info.completion_price,
                "source": pricing_info.source,
                **usage_metadata,
            },
            usage_missing=usage_missing,
            reasoning_text=self._extract_reasoning(message) if message is not None else None,
            effective_params=self._redacted_effective_params(effective),
        )

    def _call_anthropic(self, prompt: str, effective: Dict[str, Any]) -> LLMResponse:
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
            "max_tokens": effective["max_tokens"],
            "temperature": effective["temperature"],
            "timeout": effective["timeout"],
            "messages": [{"role": "user", "content": prompt}],
        }

        if effective.get("system_prompt"):
            kwargs["system"] = effective["system_prompt"]
        for key, value in effective.items():
            if key not in {
                "system_prompt",
                "temperature",
                "max_tokens",
                "timeout",
                "enable_thinking",
                "extra_body",
            }:
                kwargs[key] = value

        response = self._call_with_retry(lambda: self.client.messages.create(**kwargs))

        # Get pricing metadata for this model
        model = self._field(response, "model") or self.config.model
        pricing_info = self.pricing_manager.get_pricing(model)

        token_usage, usage_missing = self._anthropic_usage(self._field(response, "usage"))

        return LLMResponse(
            text=self._extract_text(self._field(response, "content")),
            usage=token_usage,
            model=model,
            finish_reason=self._field(response, "stop_reason"),
            pricing_metadata={
                "model": model,
                "prompt_price_per_1k": pricing_info.prompt_price,
                "completion_price_per_1k": pricing_info.completion_price,
                "source": pricing_info.source,
                "total_cost": (
                    (
                        token_usage.prompt_tokens * pricing_info.prompt_price / 1000
                        + token_usage.completion_tokens * pricing_info.completion_price / 1000
                    )
                    if not usage_missing
                    else None
                ),
                "usage_known": not usage_missing,
            },
            usage_missing=usage_missing,
            reasoning_text=self._extract_reasoning({"content": self._field(response, "content")}),
            effective_params=self._redacted_effective_params(effective),
        )

    @staticmethod
    def _redacted_effective_params(params: Dict[str, Any]) -> Dict[str, Any]:
        """Keep snapshots useful while preventing prompt/credential leakage."""
        snapshot = dict(params)
        snapshot.pop("system_prompt", None)
        normalized = {
            "temperature": snapshot.get("temperature"),
            "max_tokens": snapshot.get("max_tokens"),
            **{
                key: value
                for key, value in snapshot.items()
                if key not in {"temperature", "max_tokens", "timeout"}
            },
            "timeout": snapshot.get("timeout"),
        }
        return redact_sensitive_data(normalized)

    @staticmethod
    def _openai_usage(usage: Any) -> tuple[TokenUsage, bool]:
        """Normalize optional OpenAI usage fields without dropping a trace."""
        if usage is None:
            return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0), True
        try:
            prompt = LLMClient._field(usage, "prompt_tokens")
            completion = LLMClient._field(usage, "completion_tokens")
            if prompt is None or completion is None:
                raise ValueError("OpenAI usage fields are incomplete")
            prompt_int = int(prompt)
            completion_int = int(completion)
            total = LLMClient._field(usage, "total_tokens")
            total_int = int(total) if total is not None else prompt_int + completion_int
            reasoning_int = 0
            details = LLMClient._field(usage, "completion_tokens_details")
            raw_reasoning = (
                LLMClient._field(details, "reasoning_tokens") if details is not None else None
            )
            if raw_reasoning is not None:
                reasoning_int = max(int(raw_reasoning), 0)
            return (
                TokenUsage(
                    prompt_tokens=max(prompt_int, 0),
                    completion_tokens=max(completion_int, 0),
                    total_tokens=max(total_int, 0),
                    reasoning_tokens=reasoning_int,
                ),
                False,
            )
        except (TypeError, ValueError):
            return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0), True

    @staticmethod
    def _anthropic_usage(usage: Any) -> tuple[TokenUsage, bool]:
        """Normalize optional Anthropic usage fields without dropping a trace."""
        if usage is None:
            return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0), True
        try:
            prompt = LLMClient._field(usage, "input_tokens")
            completion = LLMClient._field(usage, "output_tokens")
            if prompt is None or completion is None:
                raise ValueError("Anthropic usage fields are incomplete")
            prompt_int = max(int(prompt), 0)
            completion_int = max(int(completion), 0)
            return (
                TokenUsage(
                    prompt_tokens=prompt_int,
                    completion_tokens=completion_int,
                    total_tokens=prompt_int + completion_int,
                ),
                False,
            )
        except (TypeError, ValueError):
            return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0), True

    def list_models(self) -> List[str]:
        """
        List model IDs from the provider's model listing endpoint.

        The listing API is free (no generation, no billing). Errors are
        re-raised with the raw reason preserved and credentials redacted.

        Returns:
            Sorted list of model IDs

        Raises:
            RuntimeError: If the listing endpoint fails
        """
        try:
            page = self.client.models.list()
        except Exception as exc:
            raise self._safe_provider_error(exc) from None
        return sorted(str(model.id) for model in page.data)

    def check_connection(self) -> Dict[str, Any]:
        """
        Verify credentials and connectivity via the model listing endpoint.

        Uses only the (free) listing API — no generation request is made, so
        the check does not incur billing. Generation-based checks would be
        billed and are the caller's responsibility to disclose.

        Returns:
            Dict with ok, provider, base_url, model_count and error fields
        """
        base_url = getattr(self.client, "base_url", None)
        result: Dict[str, Any] = {
            "ok": False,
            "provider": self.config.provider,
            "base_url": str(base_url) if base_url else None,
            "model_count": 0,
            "error": None,
        }
        try:
            models = self.list_models()
        except Exception as exc:
            result["error"] = str(exc)
            return result
        result["ok"] = True
        result["model_count"] = len(models)
        return result

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
                using_default_pricing=f"${pricing_info.prompt_price}/{pricing_info.completion_price} per 1K tokens",
            )

        cost = (
            usage.prompt_tokens * pricing_info.prompt_price / 1000
            + usage.completion_tokens * pricing_info.completion_price / 1000
        )

        return cost
