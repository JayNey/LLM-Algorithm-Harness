"""
Tests for LLMClient.
"""

import os
from unittest.mock import Mock, patch

import pytest
from pydantic import SecretStr

from src.llm_client import LLMClient
from src.models import LLMConfig, TokenUsage


@pytest.fixture
def openai_config():
    """OpenAI configuration fixture."""
    return LLMConfig(
        provider="openai",
        api_key="test-openai-key",
        model="gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=2000,
        timeout=30,
    )


@pytest.fixture
def anthropic_config():
    """Anthropic configuration fixture."""
    return LLMConfig(
        provider="anthropic",
        api_key="test-anthropic-key",
        model="claude-3-haiku",
        temperature=0.7,
        max_tokens=2000,
        timeout=30,
    )


def test_initialize_openai_client(openai_config):
    """Test initializing OpenAI client."""
    with patch("src.llm_client.OpenAI") as mock_openai:
        client = LLMClient(openai_config)

        mock_openai.assert_called_once_with(api_key="test-openai-key", max_retries=0)
        assert client.config.provider == "openai"
        assert isinstance(client._resolved_api_key, SecretStr)
        assert "test-openai-key" not in repr(client._resolved_api_key)


def test_initialize_anthropic_client(anthropic_config):
    """Test initializing Anthropic client."""
    with patch("src.llm_client.Anthropic") as mock_anthropic:
        client = LLMClient(anthropic_config)

        mock_anthropic.assert_called_once_with(api_key="test-anthropic-key", max_retries=0)
        assert client.config.provider == "anthropic"


def test_initialize_unsupported_provider():
    """Test initializing with unsupported provider raises ValidationError."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        config = LLMConfig(
            provider="unknown",
            api_key="test-key",
            model="test-model",
        )


def test_initialize_openai_missing_api_key():
    """Test initializing OpenAI without API key raises ValueError."""
    config = LLMConfig(
        provider="openai",
        api_key="",  # Empty
        model="gpt-3.5-turbo",
    )

    with patch("src.llm_client.OpenAI"):
        with patch.dict(os.environ, {}, clear=True):  # Clear env vars
            with pytest.raises(ValueError, match="API key not provided"):
                LLMClient(config)


def test_generate_openai(openai_config):
    """Test generating response with OpenAI."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        # Mock OpenAI response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.model = "gpt-3.5-turbo"

        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(openai_config)
        response = client.generate("Test prompt")

        assert response.text == "Test response"
        assert response.usage.total_tokens == 150
        assert response.model == "gpt-3.5-turbo"
        assert response.finish_reason == "stop"


def test_generate_openai_with_system_prompt(openai_config):
    """Test generating with system prompt."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.model = "gpt-3.5-turbo"

        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(openai_config)
        response = client.generate("User prompt", system_prompt="System prompt")

        # Verify system prompt was included in call
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "System prompt"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "User prompt"


def test_generate_anthropic(anthropic_config):
    """Test generating response with Anthropic."""
    with patch("src.llm_client.Anthropic") as mock_anthropic_class:
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = "Claude response"
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 120
        mock_response.usage.output_tokens = 80
        mock_response.model = "claude-3-haiku"

        mock_client.messages.create.return_value = mock_response

        client = LLMClient(anthropic_config)
        response = client.generate("Test prompt")

        assert response.text == "Claude response"
        assert response.usage.total_tokens == 200
        assert response.model == "claude-3-haiku"


def test_generate_openai_missing_usage_marks_response(openai_config):
    """Providers that omit usage produce a zeroed, explicitly marked response."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = None
        mock_response.model = "gpt-3.5-turbo"

        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(openai_config)
        response = client.generate("Test prompt")

    assert response.usage_missing is True
    assert response.usage.prompt_tokens == 0
    assert response.usage.completion_tokens == 0
    assert response.usage.total_tokens == 0


def test_generate_anthropic_missing_usage_marks_response(anthropic_config):
    """Anthropic responses without usage are zeroed and marked as well."""
    with patch("src.llm_client.Anthropic") as mock_anthropic_class:
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = "Claude response"
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        mock_response.model = "claude-3-haiku"

        mock_client.messages.create.return_value = mock_response

        client = LLMClient(anthropic_config)
        response = client.generate("Test prompt")

    assert response.usage_missing is True
    assert response.usage.total_tokens == 0


def test_generate_openai_usage_present_not_marked_missing(openai_config):
    """Responses carrying usage keep usage_missing disabled."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.model = "gpt-3.5-turbo"

        mock_client.chat.completions.create.return_value = mock_response

        client = LLMClient(openai_config)
        response = client.generate("Test prompt")

    assert response.usage_missing is False
    assert response.usage.total_tokens == 150


def test_generate_api_error(openai_config):
    """Test handling API errors during generation."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_client.chat.completions.create.side_effect = Exception("API Error")

        client = LLMClient(openai_config)

        with pytest.raises(Exception, match="API Error"):
            client.generate("Test prompt")


def test_estimate_cost_gpt35(openai_config):
    """Test estimating cost for GPT-3.5."""
    with patch("src.llm_client.OpenAI"):
        client = LLMClient(openai_config)

        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
        )

        cost = client.estimate_cost(usage)

        # Cost = (1000 * 0.0015/1000) + (500 * 0.002/1000)
        # Cost = 0.0015 + 0.001 = 0.0025
        assert abs(cost - 0.0025) < 0.0001


def test_estimate_cost_claude_haiku(anthropic_config):
    """Test estimating cost for Claude Haiku."""
    with patch("src.llm_client.Anthropic"):
        client = LLMClient(anthropic_config)

        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
        )

        cost = client.estimate_cost(usage)

        # Cost = (1000 * 0.00025/1000) + (500 * 0.00125/1000)
        # Cost = 0.00025 + 0.000625 = 0.000875
        assert abs(cost - 0.000875) < 0.000001


def test_estimate_cost_unknown_model():
    """Unknown model pricing returns None instead of a fabricated estimate."""
    config = LLMConfig(
        provider="openai",
        api_key="test-key",
        model="unknown-model",
    )

    with patch("src.llm_client.OpenAI"):
        client = LLMClient(config)

        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
        )

        cost = client.estimate_cost(usage)
        assert cost is None


def test_openai_api_key_from_env():
    """Test loading OpenAI API key from environment variable."""
    config = LLMConfig(
        provider="openai",
        api_key="",  # Empty, should use env
        model="gpt-3.5-turbo",
    )

    with patch("src.llm_client.OpenAI") as mock_openai:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            client = LLMClient(config)

            mock_openai.assert_called_once_with(api_key="env-key", max_retries=0)


def test_anthropic_api_key_from_env():
    """Test loading Anthropic API key from environment variable."""
    config = LLMConfig(
        provider="anthropic",
        api_key="",  # Empty, should use env
        model="claude-3-haiku",
    )

    with patch("src.llm_client.Anthropic") as mock_anthropic:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            client = LLMClient(config)

            mock_anthropic.assert_called_once_with(api_key="env-key", max_retries=0)


@pytest.mark.parametrize("reference", ["env:ISSUE4_API_KEY", "${ISSUE4_API_KEY}"])
def test_openai_api_key_from_explicit_environment_reference(reference):
    """Explicit references resolve only at the provider client boundary."""
    config = LLMConfig(provider="openai", api_key=reference, model="gpt-3.5-turbo")

    with patch("src.llm_client.OpenAI") as mock_openai:
        with patch.dict(os.environ, {"ISSUE4_API_KEY": "resolved-secret"}, clear=True):
            LLMClient(config)

    mock_openai.assert_called_once_with(api_key="resolved-secret", max_retries=0)
    assert "resolved-secret" not in config.model_dump_json()


def test_missing_explicit_environment_reference_does_not_dump_environment():
    """A missing reference names only the missing variable."""
    config = LLMConfig(
        provider="openai",
        api_key="env:MISSING_ISSUE4_API_KEY",
        model="gpt-3.5-turbo",
    )

    with patch("src.llm_client.OpenAI"):
        with patch.dict(os.environ, {"UNRELATED_SECRET": "must-not-leak"}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LLMClient(config)

    message = str(exc_info.value)
    assert "MISSING_ISSUE4_API_KEY" in message
    assert "must-not-leak" not in message


def test_provider_error_redacts_resolved_api_key(openai_config, capsys):
    """Provider exceptions cannot propagate a resolved API key."""
    secret = openai_config.api_key.get_secret_value()
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception(
            f"request rejected for api_key={secret}"
        )
        client = LLMClient(openai_config)

        with pytest.raises(RuntimeError) as exc_info:
            client.generate("Test prompt")

    assert secret not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)
    assert secret not in capsys.readouterr().out


def test_provider_error_uses_key_from_initialization_after_environment_changes(capsys):
    """Error cleanup uses the exact key supplied to the SDK at initialization."""
    secret = "issue4-ephemeral-environment-secret"
    config = LLMConfig(
        provider="openai",
        api_key="env:ISSUE4_EPHEMERAL_KEY",
        model="gpt-3.5-turbo",
    )
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        with patch.dict(os.environ, {"ISSUE4_EPHEMERAL_KEY": secret}, clear=True):
            client = LLMClient(config)

        mock_client.chat.completions.create.side_effect = Exception(f"provider echoed {secret}")
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                client.generate("Test prompt")

    assert secret not in str(exc_info.value)
    assert secret not in capsys.readouterr().out


# ============================================================================
# SiliconFlow provider preset tests (issue #11)
# ============================================================================


def _siliconflow_config(**overrides):
    """SiliconFlow config with empty key so env fallback is exercised."""
    payload = {"provider": "siliconflow", "api_key": "", "model": "Qwen/Qwen2.5-7B-Instruct"}
    payload.update(overrides)
    return LLMConfig(**payload)


def test_initialize_siliconflow_uses_preset_base_url_and_env_key():
    """The preset routes through the OpenAI SDK with the SiliconFlow defaults."""
    with patch("src.llm_client.OpenAI") as mock_openai:
        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "sf-env-key"}, clear=True):
            LLMClient(_siliconflow_config())

    mock_openai.assert_called_once_with(
        api_key="sf-env-key",
        base_url="https://api.siliconflow.cn/v1",
        max_retries=0,
    )


def test_siliconflow_explicit_key_and_base_url_override_preset():
    """Explicit key and base_url win over the preset and the environment."""
    config = _siliconflow_config(api_key="sf-explicit-key", base_url="https://custom.example/v1")
    with patch("src.llm_client.OpenAI") as mock_openai:
        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "sf-env-key"}, clear=True):
            LLMClient(config)

    mock_openai.assert_called_once_with(
        api_key="sf-explicit-key",
        base_url="https://custom.example/v1",
        max_retries=0,
    )


def test_siliconflow_missing_key_names_expected_env():
    """A missing key reports the SiliconFlow-specific variable."""
    with patch("src.llm_client.OpenAI"):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="SILICONFLOW_API_KEY"):
                LLMClient(_siliconflow_config())


def test_siliconflow_supports_explicit_env_reference():
    """env:NAME references keep working for SiliconFlow."""
    config = _siliconflow_config(api_key="env:MY_SF_KEY")
    with patch("src.llm_client.OpenAI") as mock_openai:
        with patch.dict(os.environ, {"MY_SF_KEY": "sf-ref-key"}, clear=True):
            LLMClient(config)

    assert mock_openai.call_args.kwargs["api_key"] == "sf-ref-key"


def test_siliconflow_provider_secret_never_serialized():
    """The resolved key stays out of model serialization."""
    with patch("src.llm_client.OpenAI"):
        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": "sf-secret-value"}, clear=True):
            client = LLMClient(_siliconflow_config())

    assert "sf-secret-value" not in client.config.model_dump_json()
    assert "sf-secret-value" not in repr(client.config)


# ============================================================================
# SiliconFlow model listing & connection check tests (issue #11)
# ============================================================================


def _siliconflow_client(env_key="sf-env-key"):
    """SiliconFlow client backed by a mocked OpenAI SDK."""
    config = _siliconflow_config()
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        with patch.dict(os.environ, {"SILICONFLOW_API_KEY": env_key}, clear=True):
            client = LLMClient(config)
    return client, mock_openai_class.return_value


def _model_page(ids):
    page = Mock()
    page.data = [Mock(id=model_id) for model_id in ids]
    return page


def test_list_models_returns_sorted_ids():
    """Model IDs come from the listing endpoint, sorted for stable output."""
    client, sdk = _siliconflow_client()
    sdk.models.list.return_value = _model_page(["Qwen/Qwen2.5-7B", "deepseek-ai/DeepSeek-V3"])

    assert client.list_models() == ["Qwen/Qwen2.5-7B", "deepseek-ai/DeepSeek-V3"]


def test_list_models_sorted_deterministically():
    """Listing is sorted alphabetically regardless of endpoint order."""
    client, sdk = _siliconflow_client()
    sdk.models.list.return_value = _model_page(["z-model", "a-model"])

    assert client.list_models() == ["a-model", "z-model"]


def test_list_models_error_keeps_reason_and_redacts_key():
    """Listing failures surface a readable, credential-free reason."""
    client, sdk = _siliconflow_client(env_key="sf-list-secret")
    sdk.models.list.side_effect = Exception("401 unauthorized for sf-list-secret")

    with pytest.raises(RuntimeError) as exc_info:
        client.list_models()

    assert "401" in str(exc_info.value)
    assert "sf-list-secret" not in str(exc_info.value)


def test_check_connection_success_without_generation():
    """Connection check uses the free listing endpoint only."""
    client, sdk = _siliconflow_client()
    sdk.base_url = "https://api.siliconflow.cn/v1"
    sdk.models.list.return_value = _model_page(["m1", "m2", "m3"])

    result = client.check_connection()

    assert result["ok"] is True
    assert result["model_count"] == 3
    assert result["base_url"] == "https://api.siliconflow.cn/v1"
    sdk.chat.completions.create.assert_not_called()


def test_check_connection_failure_returns_reason():
    """Failures return the reason instead of raising, for CLI reporting."""
    client, sdk = _siliconflow_client()
    sdk.models.list.side_effect = Exception("connection refused")

    result = client.check_connection()

    assert result["ok"] is False
    assert "connection refused" in result["error"]
    assert result["model_count"] == 0


# ============================================================================
# Unified request/response behavior (issue #12)
# ============================================================================


def test_strategy_overrides_are_sent_to_openai_request(openai_config):
    """Effective strategy values reach the provider request and are traceable."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        sdk = Mock()
        mock_openai_class.return_value = sdk
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message.content = "answer"
        response.choices[0].finish_reason = "stop"
        response.usage.prompt_tokens = 2
        response.usage.completion_tokens = 3
        response.usage.total_tokens = 5
        response.model = "gpt-3.5-turbo"
        sdk.chat.completions.create.return_value = response

        client = LLMClient(openai_config)
        result = client.generate(
            "prompt",
            system_prompt="strategy system",
            temperature=0.1,
            max_tokens=321,
            custom_params={"top_p": 0.8, "extra_body": {"foo": "bar"}},
        )

    request = sdk.chat.completions.create.call_args.kwargs
    assert request["temperature"] == 0.1
    assert request["max_tokens"] == 321
    assert request["messages"][0] == {"role": "system", "content": "strategy system"}
    assert request["top_p"] == 0.8
    assert request["extra_body"] == {"foo": "bar"}
    assert result.effective_params == {
        "temperature": 0.1,
        "max_tokens": 321,
        "top_p": 0.8,
        "extra_body": {"foo": "bar"},
        "timeout": 30,
    }


def test_openai_content_blocks_and_reasoning_are_normalized(openai_config):
    """Multiple text blocks and optional reasoning do not lose the response."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        sdk = Mock()
        mock_openai_class.return_value = sdk
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message.content = [
            {"type": "text", "text": "```python\n"},
            {"type": "text", "text": "def solution():\n    return 1\n```"},
        ]
        response.choices[0].message.reasoning_content = "reasoning"
        response.choices[0].finish_reason = "stop"
        response.usage = None
        response.model = "gpt-3.5-turbo"
        sdk.chat.completions.create.return_value = response

        result = LLMClient(openai_config).generate("prompt")

    assert result.text.startswith("```python")
    assert result.reasoning_text == "reasoning"
    assert result.usage_missing is True
    assert result.pricing_metadata["usage_known"] is False
    assert result.pricing_metadata["total_cost"] is None


def test_openai_dict_response_fixture_is_supported(openai_config):
    """Compatibility fixtures can use plain dictionaries like raw JSON."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        sdk = Mock()
        mock_openai_class.return_value = sdk
        sdk.chat.completions.create.return_value = {
            "choices": [
                {
                    "message": {"content": [{"type": "text", "text": "answer"}]},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "model": "gpt-3.5-turbo",
        }

        result = LLMClient(openai_config).generate("prompt")

    assert result.text == "answer"
    assert result.usage.total_tokens == 3


def test_retryable_provider_error_is_bounded(openai_config):
    """429 retries stop after the configured total attempts."""
    openai_config.retry_backoff_seconds = 0
    openai_config.retry_max_attempts = 3

    class RateLimitError(Exception):
        status_code = 429

    with patch("src.llm_client.OpenAI") as mock_openai_class:
        sdk = Mock()
        mock_openai_class.return_value = sdk
        sdk.chat.completions.create.side_effect = RateLimitError("busy")
        client = LLMClient(openai_config)

        with pytest.raises(RuntimeError, match="busy"):
            client.generate("prompt")

    assert sdk.chat.completions.create.call_count == 3


def test_authentication_error_is_not_retried(openai_config):
    """401 errors fail immediately instead of multiplying invalid requests."""

    class UnauthorizedError(Exception):
        status_code = 401

    with patch("src.llm_client.OpenAI") as mock_openai_class:
        sdk = Mock()
        mock_openai_class.return_value = sdk
        sdk.chat.completions.create.side_effect = UnauthorizedError("unauthorized")
        client = LLMClient(openai_config)

        with pytest.raises(RuntimeError, match="unauthorized"):
            client.generate("prompt")

    assert sdk.chat.completions.create.call_count == 1


def test_anthropic_request_receives_timeout(anthropic_config):
    """Anthropic timeout is applied to the actual messages request."""
    with patch("src.llm_client.Anthropic") as mock_anthropic_class:
        sdk = Mock()
        mock_anthropic_class.return_value = sdk
        response = Mock()
        response.content = [{"type": "text", "text": "answer"}]
        response.stop_reason = "end_turn"
        response.usage = None
        response.model = "claude-3-haiku"
        sdk.messages.create.return_value = response

        LLMClient(anthropic_config).generate("prompt")

    assert sdk.messages.create.call_args.kwargs["timeout"] == 30


def test_anthropic_thinking_block_stays_out_of_answer_text(anthropic_config):
    """Anthropic thinking and answer blocks remain distinguishable."""
    with patch("src.llm_client.Anthropic") as mock_anthropic_class:
        sdk = Mock()
        mock_anthropic_class.return_value = sdk
        response = Mock()
        response.content = [
            {"type": "thinking", "thinking": "internal plan"},
            {"type": "text", "text": "final answer"},
        ]
        response.stop_reason = "end_turn"
        response.usage = Mock(input_tokens=4, output_tokens=2)
        response.model = "claude-3-haiku"
        sdk.messages.create.return_value = response

        result = LLMClient(anthropic_config).generate("prompt")

    assert result.text == "final answer"
    assert result.reasoning_text == "internal plan"
    assert result.usage_missing is False


def test_incomplete_usage_is_marked_unknown(openai_config):
    """Malformed usage metadata is unknown instead of raising or charging zero."""
    with patch("src.llm_client.OpenAI") as mock_openai_class:
        sdk = Mock()
        mock_openai_class.return_value = sdk
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message.content = "answer"
        response.choices[0].finish_reason = "length"
        response.usage = Mock(prompt_tokens=10)
        response.model = "gpt-3.5-turbo"
        sdk.chat.completions.create.return_value = response

        result = LLMClient(openai_config).generate("prompt")

    assert result.usage_missing is True
    assert result.pricing_metadata["usage_known"] is False
    assert result.pricing_metadata["total_cost"] is None


def test_local_provider_requires_explicit_openai_compatible_endpoint():
    """The local provider declaration matches its OpenAI-compatible behavior."""
    config = LLMConfig(provider="local", api_key="local-key", model="local-model")
    with patch("src.llm_client.OpenAI"):
        with pytest.raises(ValueError, match="provider=local requires base_url"):
            LLMClient(config)

    config.base_url = "http://localhost:8000/v1"
    with patch("src.llm_client.OpenAI") as mock_openai:
        client = LLMClient(config)
    mock_openai.assert_called_once_with(
        api_key="local-key", base_url="http://localhost:8000/v1", max_retries=0
    )
    assert client.config.provider == "local"


def test_local_provider_can_use_empty_key_for_unauthenticated_server():
    """Unauthenticated local servers receive a harmless SDK placeholder key."""
    config = LLMConfig(
        provider="local",
        api_key="",
        model="local-model",
        base_url="http://localhost:8000/v1",
    )
    with patch("src.llm_client.OpenAI") as mock_openai:
        with patch.dict(os.environ, {}, clear=True):
            LLMClient(config)
    assert mock_openai.call_args.kwargs["api_key"] == "local"
