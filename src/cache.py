"""
LLM Response Cache Module

Provides caching functionality for LLM API responses to reduce costs
and improve experiment reproducibility.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from src.models import LLMResponse, TokenUsage

DEFAULT_CACHE_DIR = ".cache/llm_responses"
# Environment override for the cache location; tests use it to isolate the
# disk-backed cache per test, and deployments can redirect it without config.
CACHE_DIR_ENV = "LLM_CACHE_DIR"


class CacheKey:
    """Generate unique cache keys based on LLM request parameters."""

    @staticmethod
    def generate(
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        problem_id: str | None = None,
        strategy_name: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """
        Generate a SHA256-based cache key from request parameters.

        Args:
            model: Model identifier
            prompt: User prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            problem_id: Optional problem identifier
            strategy_name: Optional strategy name
            system_prompt: Optional system prompt

        Returns:
            Hexadecimal cache key string
        """
        # Build canonical parameter string
        params = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if system_prompt is not None:
            params["system_prompt"] = system_prompt

        if problem_id is not None:
            params["problem_id"] = problem_id

        if strategy_name is not None:
            params["strategy_name"] = strategy_name

        # Sort keys for deterministic serialization
        canonical = json.dumps(params, sort_keys=True, ensure_ascii=True)

        # Generate SHA256 hash
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LLMResponseCache:
    """Local disk-based cache for LLM responses."""

    def __init__(
        self,
        cache_dir: str = DEFAULT_CACHE_DIR,
        ttl_days: int = 30,
        max_size_mb: int = 1000,
        enabled: bool = True,
    ):
        """
        Initialize the LLM response cache.

        Args:
            cache_dir: Directory for cache storage
            ttl_days: Time-to-live in days
            max_size_mb: Maximum cache size in MB
            enabled: Whether caching is enabled
        """
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_days * 86400
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.enabled = enabled
        self.access_log_path = self.cache_dir / ".access_log.json"

        # Statistics
        self.hits = 0
        self.misses = 0
        self.api_calls_saved = 0

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._init_access_log()

    def _init_access_log(self):
        """Initialize access log file if it doesn't exist."""
        if not self.access_log_path.exists():
            self._write_access_log({})

    def _read_access_log(self) -> dict[str, float]:
        """Read the access log."""
        try:
            if self.access_log_path.exists():
                with open(self.access_log_path) as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _write_access_log(self, log: dict[str, float]):
        """Write the access log atomically."""
        temp_path = self.access_log_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(log, f)
        temp_path.replace(self.access_log_path)

    def _update_access_time(self, cache_key: str):
        """Update access time for LRU tracking."""
        log = self._read_access_log()
        log[cache_key] = time.time()
        self._write_access_log(log)

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def _is_expired(self, cache_data: dict[str, Any]) -> bool:
        """Check if a cache entry is expired."""
        timestamp = cache_data.get("timestamp", 0)
        age_seconds = time.time() - timestamp
        return age_seconds >= self.ttl_seconds

    def get(self, cache_key: str) -> LLMResponse | None:
        """
        Retrieve a cached response.

        Args:
            cache_key: Cache key to look up

        Returns:
            Cached LLMResponse if found and not expired, None otherwise
        """
        if not self.enabled:
            return None

        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            self.misses += 1
            return None

        try:
            with open(cache_path) as f:
                cache_data = json.load(f)

            # Check expiration
            if self._is_expired(cache_data):
                self.misses += 1
                return None

            # Update access time for LRU
            self._update_access_time(cache_key)

            # Reconstruct LLMResponse
            response = LLMResponse(
                text=cache_data["response_text"],
                usage=TokenUsage(**cache_data["token_usage"]),
                model=cache_data["model"],
                finish_reason=cache_data.get("finish_reason"),
                pricing_metadata=cache_data.get("pricing_metadata"),
                usage_missing=cache_data.get("usage_missing", False),
                reasoning_text=cache_data.get("reasoning_text"),
                effective_params=cache_data.get("effective_params", {}),
            )

            self.hits += 1
            self.api_calls_saved += 1
            return response

        except (OSError, json.JSONDecodeError, KeyError):
            self.misses += 1
            return None

    def set(self, cache_key: str, response: LLMResponse):
        """
        Store a response in the cache.

        Args:
            cache_key: Cache key
            response: LLMResponse to cache
        """
        if not self.enabled:
            return

        cache_data = {
            "response_text": response.text,
            "token_usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "reasoning_tokens": response.usage.reasoning_tokens,
            },
            "timestamp": time.time(),
            "model": response.model,
            "finish_reason": response.finish_reason,
            "pricing_metadata": response.pricing_metadata,
            "usage_missing": response.usage_missing,
            "reasoning_text": response.reasoning_text,
            "effective_params": response.effective_params,
        }

        cache_path = self._get_cache_path(cache_key)

        # Atomic write: write to temp file then rename
        temp_path = cache_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w") as f:
                json.dump(cache_data, f, indent=2)
            temp_path.replace(cache_path)

            # Update access log
            self._update_access_time(cache_key)

            # Check and enforce size limit
            self._enforce_size_limit()

        except OSError:
            if temp_path.exists():
                temp_path.unlink()

    def _get_cache_size_bytes(self) -> int:
        """Calculate total cache size in bytes."""
        total_size = 0
        for cache_file in self.cache_dir.glob("*.json"):
            if cache_file.name != ".access_log.json":
                total_size += cache_file.stat().st_size
        return total_size

    def _enforce_size_limit(self):
        """Enforce LRU eviction when cache exceeds size limit."""
        current_size = self._get_cache_size_bytes()

        if current_size <= self.max_size_bytes:
            return

        # Load access log
        access_log = self._read_access_log()

        # Get all cache files with their access times
        cache_files = []
        for cache_file in self.cache_dir.glob("*.json"):
            if cache_file.name != ".access_log.json":
                cache_key = cache_file.stem
                access_time = access_log.get(cache_key, 0)
                file_size = cache_file.stat().st_size
                cache_files.append((access_time, cache_key, file_size, cache_file))

        # Sort by access time (oldest first)
        cache_files.sort(key=lambda x: x[0])

        # Evict oldest entries until under size limit
        for access_time, cache_key, file_size, cache_file in cache_files:
            if current_size <= self.max_size_bytes:
                break

            try:
                cache_file.unlink()
                current_size -= file_size

                # Remove from access log
                if cache_key in access_log:
                    del access_log[cache_key]

            except OSError:
                pass

        # Write updated access log
        self._write_access_log(access_log)

    def clear(self, model_filter: str | None = None):
        """
        Clear cache entries.

        Args:
            model_filter: If provided, only clear entries for this model
        """
        if not self.enabled:
            return

        if model_filter is None:
            # Clear all cache files
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.name != ".access_log.json":
                    cache_file.unlink()
            self._write_access_log({})
        else:
            # Clear only entries matching the model
            access_log = self._read_access_log()
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.name == ".access_log.json":
                    continue

                try:
                    with open(cache_file) as f:
                        cache_data = json.load(f)

                    if cache_data.get("model") == model_filter:
                        cache_file.unlink()
                        cache_key = cache_file.stem
                        if cache_key in access_log:
                            del access_log[cache_key]

                except (OSError, json.JSONDecodeError):
                    pass

            self._write_access_log(access_log)

    def stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        if not self.enabled:
            return {
                "enabled": False,
                "total_entries": 0,
                "disk_usage_mb": 0.0,
                "hit_rate": 0.0,
                "hits": 0,
                "misses": 0,
                "api_calls_saved": 0,
            }

        total_entries = len(list(self.cache_dir.glob("*.json"))) - 1  # Exclude access log
        disk_usage_bytes = self._get_cache_size_bytes()
        disk_usage_mb = disk_usage_bytes / (1024 * 1024)

        total_requests = self.hits + self.misses
        hit_rate = self.hits / total_requests if total_requests > 0 else 0.0

        return {
            "enabled": True,
            "total_entries": max(0, total_entries),
            "disk_usage_mb": disk_usage_mb,
            "hit_rate": hit_rate,
            "hits": self.hits,
            "misses": self.misses,
            "api_calls_saved": self.api_calls_saved,
        }
