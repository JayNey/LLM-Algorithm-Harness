"""
Problem and dataset fingerprint calculation for incremental evaluation.
"""

import hashlib
import json
import os
import sys
from typing import Any

from src.models import JUDGE_CONTRACT_VERSION, HarnessConfig, LLMConfig, Problem

# Bump when generation, strategy, sandbox, or result semantics change in a way
# that is not represented by the hashed configuration or the judge contract.
EXECUTION_FINGERPRINT_VERSION = 1


def hash_json(content: Any) -> str:
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _llm_identity(config: LLMConfig) -> dict[str, Any]:
    # Follow the provider initialization in LLMClient. The OpenAI and
    # Anthropic SDKs also accept endpoints and routing inputs from the environment.
    provider = config.provider
    base_url = config.base_url
    routing: dict[str, str | None] = {}
    key_env = f"{provider.upper()}_API_KEY"
    if provider in {"openai", "local", "deepseek", "siliconflow"}:
        routing = {name: os.getenv(name) for name in ("OPENAI_ORG_ID", "OPENAI_PROJECT_ID")}
    if provider == "openai" and not base_url:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    elif provider == "local":
        key_env = "OPENAI_API_KEY"
    elif provider == "deepseek" and (
        not base_url
        or base_url.rstrip("/") in {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
    ):
        base_url = "https://api.deepseek.com"
    elif provider == "siliconflow" and not base_url:
        base_url = "https://api.siliconflow.cn/v1"
    elif provider == "anthropic":
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        routing = {
            name: os.getenv(name) for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS")
        }

    configured_key = config.api_key.get_secret_value()
    key: str | None = configured_key
    if configured_key.startswith("env:"):
        key = os.getenv(configured_key[4:])
    elif configured_key.startswith("${") and configured_key.endswith("}"):
        key = os.getenv(configured_key[2:-1])
    elif not configured_key:
        key = os.getenv(key_env) or ("local" if provider == "local" else None)
    return {"base_url": base_url, "routing": routing, "credential": key}


def compute_execution_fingerprint(config: HarnessConfig) -> str:
    """Hash effective execution inputs. Only the digest may be persisted."""
    payload = config.model_dump(
        exclude={
            "llm_config": {"api_key", "base_url"},
            "dataset_path": True,
            "output_dir": True,
            "log_level": True,
            "problem_filters": True,  # The selected problem fingerprints cover this.
            "enable_incremental": True,
            "cost_alerts": True,
        },
    )
    payload["llm_config"].update(_llm_identity(config.llm_config))
    payload["execution_fingerprint_version"] = EXECUTION_FINGERPRINT_VERSION
    payload["judge_contract_version"] = JUDGE_CONTRACT_VERSION
    if config.sandbox_config.backend == "host":
        payload["host_python_version"] = sys.version_info[:3]
    return hash_json(payload)


def compute_problem_fingerprint(problem: Problem) -> str:
    """Hash normalized evaluation inputs, excluding audit-only import fields."""
    fields = {
        "problem_id",
        "title",
        "description",
        "difficulty",
        "tags",
        "constraints",
        "unsupported_reason",
        "input_output_mode",
        "entry_point",
        "public_test_cases",
        "feedback_test_cases",
        "hidden_test_cases",
        "judge_config",
    }
    content = problem.model_dump(include=fields)
    content["judge_contract_version"] = JUDGE_CONTRACT_VERSION
    return hash_json(content)


def compute_dataset_fingerprint(problems: list[Problem]) -> dict[str, str]:
    """
    Generate fingerprint mapping for an entire dataset.

    Args:
        problems: List of Problem instances

    Returns:
        Dict mapping problem_id to its fingerprint

    Example:
        >>> fingerprints = compute_dataset_fingerprint(problems)
        >>> fingerprints
        {'two_sum': 'abc123...', 'reverse_string': 'def456...'}
    """
    return {problem.problem_id: compute_problem_fingerprint(problem) for problem in problems}
