"""Unit tests for LLMClient cache integration."""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.llm_client import LLMClient
from src.models import CacheConfig, LLMConfig, LLMResponse, TokenUsage


class TestLLMClientCache:
    """Test LLMClient cache integration."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def cache_config(self):
        """Create cache configuration."""
        return CacheConfig(
            enabled=True,
            backend="disk",
            ttl_days=7,
            max_size_mb=100,
        )

    @pytest.fixture
    def llm_config_with_cache(self, cache_config):
        """Create LLM configuration with caching enabled."""
        return LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="test-key",
            temperature=0.7,
            max_tokens=100,
            cache=cache_config,
        )

    @pytest.fixture
    def llm_config_without_cache(self):
        """Create LLM configuration with caching disabled."""
        return LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="test-key",
            temperature=0.7,
            max_tokens=100,
            cache=CacheConfig(enabled=False),
        )

    @pytest.fixture
    def sample_response(self):
        """Create a sample LLM response."""
        return LLMResponse(
            text="Sample answer",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            model="gpt-4",
            finish_reason="stop",
            pricing_metadata={
                "model": "gpt-4",
                "prompt_price_per_1k": 0.03,
                "completion_price_per_1k": 0.06,
                "source": "config",
                "as_of": "2024-01-01",
                "pricing_known": True,
                "total_cost": 0.0015,
                "usage_known": True,
            },
            usage_missing=False,
            reasoning_text=None,
            effective_params={"temperature": 0.7, "max_tokens": 100},
        )

    @patch("src.llm_client.OpenAI")
    def test_cache_miss_calls_api(self, mock_openai, temp_cache_dir):
        """Cache miss should call the API."""
        # Create config with isolated cache
        cache_config = CacheConfig(
            enabled=True,
            backend="disk",
            ttl_days=7,
            max_size_mb=100,
        )
        llm_config = LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="test-key",
            temperature=0.7,
            max_tokens=100,
            cache=cache_config,
        )

        # Setup mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sample answer"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.usage.completion_tokens_details = None
        mock_client.chat.completions.create.return_value = mock_response

        # Patch cache to use temp directory
        from src.cache import LLMResponseCache
        from src.utils.pricing import PricingManager

        def patched_init(self, config):
            self.config = config
            self._resolved_api_key = None
            self.client = mock_client
            self.pricing_manager = PricingManager()
            self.cache = LLMResponseCache(
                cache_dir=temp_cache_dir,
                ttl_days=config.cache.ttl_days,
                max_size_mb=config.cache.max_size_mb,
                enabled=config.cache.enabled,
            )

        with patch.object(LLMClient, "__init__", patched_init):
            client = LLMClient(llm_config)

            # First call should hit API
            response = client.generate("Test prompt")

            # Verify API was called
            assert mock_client.chat.completions.create.call_count == 1
            assert response.text == "Sample answer"

    @patch("src.llm_client.OpenAI")
    def test_cache_hit_skips_api(self, mock_openai, temp_cache_dir):
        """Cache hit should skip the API call."""
        # Create config with isolated temporary cache directory
        cache_config = CacheConfig(
            enabled=True,
            backend="disk",
            ttl_days=7,
            max_size_mb=100,
        )
        llm_config = LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="test-key",
            temperature=0.7,
            max_tokens=100,
            cache=cache_config,
        )

        # Setup mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sample answer"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.usage.completion_tokens_details = None
        mock_client.chat.completions.create.return_value = mock_response

        # Patch cache initialization to use temp directory
        from src.cache import LLMResponseCache

        original_init = LLMClient.__init__

        def patched_init(self, config):
            self.config = config
            self._resolved_api_key = None
            self.client = mock_client
            from src.utils.pricing import PricingManager

            self.pricing_manager = PricingManager()
            # Use temp_cache_dir instead of default
            self.cache = LLMResponseCache(
                cache_dir=temp_cache_dir,
                ttl_days=config.cache.ttl_days,
                max_size_mb=config.cache.max_size_mb,
                enabled=config.cache.enabled,
            )

        with patch.object(LLMClient, "__init__", patched_init):
            client = LLMClient(llm_config)

            # First call should hit API
            response1 = client.generate("Test prompt unique", temperature=0.7, max_tokens=100)
            assert mock_client.chat.completions.create.call_count == 1

            # Second call with same parameters should hit cache
            response2 = client.generate("Test prompt unique", temperature=0.7, max_tokens=100)
            assert mock_client.chat.completions.create.call_count == 1  # No additional call

            # Responses should be identical
            assert response1.text == response2.text
            assert response1.usage.total_tokens == response2.usage.total_tokens

    @patch("src.llm_client.OpenAI")
    def test_disabled_cache_always_calls_api(self, mock_openai, llm_config_without_cache):
        """Disabled cache should always call the API."""
        # Setup mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sample answer"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.usage.completion_tokens_details = None
        mock_client.chat.completions.create.return_value = mock_response

        # Create client
        client = LLMClient(llm_config_without_cache)

        # First call
        client.generate("Test prompt")
        assert mock_client.chat.completions.create.call_count == 1

        # Second call should also hit API
        client.generate("Test prompt")
        assert mock_client.chat.completions.create.call_count == 2

    @patch("src.llm_client.OpenAI")
    def test_problem_id_affects_cache_key(self, mock_openai, temp_cache_dir):
        """Different problem_id should create separate cache entries."""
        # Create config with isolated cache
        cache_config = CacheConfig(
            enabled=True,
            backend="disk",
            ttl_days=7,
            max_size_mb=100,
        )
        llm_config = LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="test-key",
            temperature=0.7,
            max_tokens=100,
            cache=cache_config,
        )

        # Setup mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sample answer"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.usage.completion_tokens_details = None
        mock_client.chat.completions.create.return_value = mock_response

        # Patch cache to use temp directory
        from src.cache import LLMResponseCache
        from src.utils.pricing import PricingManager

        def patched_init(self, config):
            self.config = config
            self._resolved_api_key = None
            self.client = mock_client
            self.pricing_manager = PricingManager()
            self.cache = LLMResponseCache(
                cache_dir=temp_cache_dir,
                ttl_days=config.cache.ttl_days,
                max_size_mb=config.cache.max_size_mb,
                enabled=config.cache.enabled,
            )

        with patch.object(LLMClient, "__init__", patched_init):
            client = LLMClient(llm_config)

            # Call with problem_id="problem1"
            client.generate("Test prompt", problem_id="problem1")
            assert mock_client.chat.completions.create.call_count == 1

            # Same prompt but different problem_id should call API again
            client.generate("Test prompt", problem_id="problem2")
            assert mock_client.chat.completions.create.call_count == 2

    @patch("src.llm_client.OpenAI")
    def test_strategy_name_affects_cache_key(self, mock_openai, temp_cache_dir):
        """Different strategy_name should create separate cache entries."""
        # Create config with isolated cache
        cache_config = CacheConfig(
            enabled=True,
            backend="disk",
            ttl_days=7,
            max_size_mb=100,
        )
        llm_config = LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="test-key",
            temperature=0.7,
            max_tokens=100,
            cache=cache_config,
        )

        # Setup mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sample answer"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.usage.completion_tokens_details = None
        mock_client.chat.completions.create.return_value = mock_response

        # Patch cache to use temp directory
        from src.cache import LLMResponseCache
        from src.utils.pricing import PricingManager

        def patched_init(self, config):
            self.config = config
            self._resolved_api_key = None
            self.client = mock_client
            self.pricing_manager = PricingManager()
            self.cache = LLMResponseCache(
                cache_dir=temp_cache_dir,
                ttl_days=config.cache.ttl_days,
                max_size_mb=config.cache.max_size_mb,
                enabled=config.cache.enabled,
            )

        with patch.object(LLMClient, "__init__", patched_init):
            client = LLMClient(llm_config)

            # Call with strategy_name="cot"
            client.generate("Test prompt", strategy_name="cot")
            assert mock_client.chat.completions.create.call_count == 1

            # Same prompt but different strategy_name should call API again
            client.generate("Test prompt", strategy_name="direct")
            assert mock_client.chat.completions.create.call_count == 2
