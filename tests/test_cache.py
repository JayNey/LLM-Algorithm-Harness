"""Unit tests for LLM response caching."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from src.cache import CacheKey, LLMResponseCache
from src.models import LLMResponse, TokenUsage


class TestCacheKey:
    """Test cache key generation."""

    def test_same_params_same_key(self):
        """Identical parameters should generate identical keys."""
        key1 = CacheKey.generate(
            model="gpt-4",
            prompt="Hello world",
            temperature=0.7,
            max_tokens=100,
        )
        key2 = CacheKey.generate(
            model="gpt-4",
            prompt="Hello world",
            temperature=0.7,
            max_tokens=100,
        )
        assert key1 == key2

    def test_different_params_different_keys(self):
        """Different parameters should generate different keys."""
        key1 = CacheKey.generate(
            model="gpt-4",
            prompt="Hello world",
            temperature=0.7,
            max_tokens=100,
        )
        key2 = CacheKey.generate(
            model="gpt-4",
            prompt="Hello world",
            temperature=0.8,  # Different temperature
            max_tokens=100,
        )
        assert key1 != key2

    def test_optional_params(self):
        """Optional parameters should affect the key."""
        key1 = CacheKey.generate(
            model="gpt-4",
            prompt="Test",
            temperature=0.7,
            max_tokens=100,
        )
        key2 = CacheKey.generate(
            model="gpt-4",
            prompt="Test",
            temperature=0.7,
            max_tokens=100,
            problem_id="problem123",
        )
        assert key1 != key2

    def test_problem_and_strategy_in_key(self):
        """Problem ID and strategy name should be included in the key."""
        key = CacheKey.generate(
            model="gpt-4",
            prompt="Test",
            temperature=0.7,
            max_tokens=100,
            problem_id="problem123",
            strategy_name="cot",
        )
        # Key should be a 64-character hex string (SHA256)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


class TestLLMResponseCache:
    """Test LLM response cache operations."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def cache(self, temp_cache_dir):
        """Create a cache instance with temporary directory."""
        return LLMResponseCache(
            cache_dir=temp_cache_dir,
            ttl_days=7,
            max_size_mb=100,
            enabled=True,
        )

    @pytest.fixture
    def sample_response(self):
        """Create a sample LLM response."""
        return LLMResponse(
            text="Sample response",
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

    def test_cache_miss(self, cache):
        """Cache miss should return None."""
        key = "nonexistent_key"
        result = cache.get(key)
        assert result is None

    def test_set_and_get(self, cache, sample_response):
        """Set and get should work correctly."""
        key = CacheKey.generate(
            model="gpt-4",
            prompt="Test",
            temperature=0.7,
            max_tokens=100,
        )

        # Set cache
        cache.set(key, sample_response)

        # Get cache
        result = cache.get(key)
        assert result is not None
        assert result.text == sample_response.text
        assert result.usage.total_tokens == sample_response.usage.total_tokens
        assert result.model == sample_response.model

    def test_cache_expiry(self, temp_cache_dir, sample_response):
        """Expired cache entries should return None."""
        # Create cache with very short TTL
        cache = LLMResponseCache(
            cache_dir=temp_cache_dir,
            ttl_days=0.00001,  # ~0.86 seconds
            enabled=True,
        )

        key = CacheKey.generate(
            model="gpt-4",
            prompt="Test",
            temperature=0.7,
            max_tokens=100,
        )

        # Set cache
        cache.set(key, sample_response)

        # Should hit immediately
        result = cache.get(key)
        assert result is not None

        # Wait for expiry
        time.sleep(1.5)

        # Should miss after expiry
        result = cache.get(key)
        assert result is None

    def test_disabled_cache(self, temp_cache_dir, sample_response):
        """Disabled cache should not store or retrieve."""
        cache = LLMResponseCache(
            cache_dir=temp_cache_dir,
            enabled=False,
        )

        key = CacheKey.generate(
            model="gpt-4",
            prompt="Test",
            temperature=0.7,
            max_tokens=100,
        )

        # Set should be no-op
        cache.set(key, sample_response)

        # Get should always miss
        result = cache.get(key)
        assert result is None

    def test_clear_all(self, cache, sample_response):
        """Clear should remove all cache entries."""
        key1 = CacheKey.generate(model="gpt-4", prompt="Test1", temperature=0.7, max_tokens=100)
        key2 = CacheKey.generate(model="gpt-3.5-turbo", prompt="Test2", temperature=0.7, max_tokens=100)

        cache.set(key1, sample_response)
        cache.set(key2, sample_response)

        # Verify both exist
        assert cache.get(key1) is not None
        assert cache.get(key2) is not None

        # Clear all
        cache.clear()

        # Verify both gone
        assert cache.get(key1) is None
        assert cache.get(key2) is None

    def test_clear_by_model(self, cache, sample_response):
        """Clear with model filter should only remove matching entries."""
        key1 = CacheKey.generate(model="gpt-4", prompt="Test1", temperature=0.7, max_tokens=100)

        # Create response for gpt-3.5-turbo
        response2 = LLMResponse(
            text="Sample response 2",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            model="gpt-3.5-turbo",
            finish_reason="stop",
            pricing_metadata={
                "model": "gpt-3.5-turbo",
                "prompt_price_per_1k": 0.001,
                "completion_price_per_1k": 0.002,
                "source": "config",
                "as_of": "2024-01-01",
                "pricing_known": True,
                "total_cost": 0.00005,
                "usage_known": True,
            },
            usage_missing=False,
            reasoning_text=None,
            effective_params={"temperature": 0.7, "max_tokens": 100},
        )
        key2 = CacheKey.generate(model="gpt-3.5-turbo", prompt="Test2", temperature=0.7, max_tokens=100)

        cache.set(key1, sample_response)
        cache.set(key2, response2)

        # Clear only gpt-4
        cache.clear(model_filter="gpt-4")

        # gpt-4 should be gone, gpt-3.5-turbo should remain
        assert cache.get(key1) is None
        assert cache.get(key2) is not None

    def test_stats(self, cache, sample_response):
        """Stats should return accurate cache statistics."""
        stats = cache.stats()
        assert stats["enabled"] is True
        assert stats["total_entries"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        key = CacheKey.generate(model="gpt-4", prompt="Test", temperature=0.7, max_tokens=100)

        # Miss
        cache.get(key)
        stats = cache.stats()
        assert stats["misses"] == 1

        # Set and hit
        cache.set(key, sample_response)
        cache.get(key)
        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["hits"] == 1
        assert stats["api_calls_saved"] == 1
        assert stats["disk_usage_mb"] > 0

    def test_lru_eviction(self, temp_cache_dir, sample_response):
        """LRU eviction should remove least recently accessed entries."""
        # Create cache with very small size limit
        cache = LLMResponseCache(
            cache_dir=temp_cache_dir,
            max_size_mb=0.001,  # 1KB
            enabled=True,
        )

        # Create multiple entries
        keys = []
        for i in range(5):
            key = CacheKey.generate(
                model="gpt-4",
                prompt=f"Test prompt {i}" * 100,  # Make it larger
                temperature=0.7,
                max_tokens=100,
            )
            keys.append(key)
            cache.set(key, sample_response)
            time.sleep(0.1)  # Ensure different access times

        # Some entries should be evicted
        stats = cache.stats()
        assert stats["total_entries"] < 5

