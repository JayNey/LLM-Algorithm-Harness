"""
Tests for LLMClient.
"""

import os
from unittest.mock import Mock, patch

import pytest

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

        mock_openai.assert_called_once_with(api_key="test-openai-key", max_retries=3)
        assert client.config.provider == "openai"


def test_initialize_anthropic_client(anthropic_config):
    """Test initializing Anthropic client."""
    with patch("src.llm_client.Anthropic") as mock_anthropic:
        client = LLMClient(anthropic_config)

        mock_anthropic.assert_called_once_with(api_key="test-anthropic-key")
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
    """Test estimating cost for unknown model returns 0."""
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
        assert cost == 0.0


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

            mock_openai.assert_called_once_with(api_key="env-key", max_retries=3)


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

            mock_anthropic.assert_called_once_with(api_key="env-key")
