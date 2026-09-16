"""Configuration utilities for loading and managing configuration."""

from pathlib import Path
from typing import Any

import yaml

from src.models import HarnessConfig


def load_config(config_path: str, overrides: dict[str, Any] | None = None) -> HarnessConfig:
    """
    Load configuration from a JSON or YAML file.

    Args:
        config_path: Path to configuration file
        overrides: Explicit values to merge before model validation

    Returns:
        HarnessConfig object

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML/JSON is malformed
        ValueError: If the document root is not a mapping
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    if not isinstance(config_data, dict):
        raise ValueError("Configuration document must be a mapping")

    if overrides:
        config_data = merge_configs(config_data, overrides, {})

    return HarnessConfig(**config_data)


def merge_configs(
    default_config: dict[str, Any],
    user_config: dict[str, Any],
    env_overrides: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge multiple configuration layers.

    Priority: env_overrides > user_config > default_config

    Args:
        default_config: Default configuration
        user_config: User-provided configuration
        env_overrides: Environment variable overrides

    Returns:
        Merged configuration dictionary
    """
    merged = default_config.copy()

    # Apply user config
    for key, value in user_config.items():
        if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value

    # Apply env overrides
    for key, value in env_overrides.items():
        if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value

    return merged


def validate_config(config_dict: dict[str, Any]) -> bool:
    """
    Validate configuration completeness.

    Args:
        config_dict: Configuration dictionary

    Returns:
        True if valid

    Raises:
        ValueError: If configuration is invalid
    """
    required_keys = ["llm_config", "output_dir"]

    for key in required_keys:
        if key not in config_dict:
            raise ValueError(f"Missing required configuration key: {key}")

    if "llm_config" in config_dict:
        llm_required = ["provider", "api_key", "model"]
        for key in llm_required:
            if key not in config_dict["llm_config"]:
                raise ValueError(f"Missing required LLM config key: {key}")

    return True


def get_default_config() -> dict[str, Any]:
    """
    Get default configuration.

    Returns:
        Default configuration dictionary
    """
    return {
        "llm_config": {
            "provider": "openai",
            "api_key": "",
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 2000,
            "timeout": 30,
        },
        "sandbox_config": {
            "timeout_seconds": 5,
            "memory_limit_mb": 256,
            "allowed_imports": ["math", "itertools", "collections", "heapq", "bisect", "functools"],
        },
        "output_dir": "./results",
        "max_workers": 5,
        "log_level": "INFO",
    }
