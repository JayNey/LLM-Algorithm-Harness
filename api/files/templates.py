"""Non-secret configuration templates validated by the same upload schemas."""

import copy
from typing import Any

from fastapi import HTTPException
from pydantic import SecretStr

from src.models import ExperimentConfig, HarnessConfig, LLMConfig, StrategyConfig

LLM = LLMConfig(provider="openai", api_key=SecretStr("[REDACTED]"), model="gpt-4o-mini")
TEMPLATES: dict[str, dict[str, Any]] = {
    "vanilla": {
        "type": "harness",
        "config": HarnessConfig(
            llm_config=LLM,
            dataset_path="problems.json",
            strategies=[StrategyConfig(name="vanilla")],
        ).redacted_dict(),
    },
    "experiment": {
        "type": "experiment",
        "config": ExperimentConfig(
            dataset_path="problems.json",
            models=[LLM],
            strategies=[StrategyConfig(name="vanilla")],
            repeats=1,
        ).redacted_dict(),
    },
}


def template(name: str) -> dict:
    if name not in TEMPLATES:
        raise HTTPException(404, "Template not found")
    return copy.deepcopy(TEMPLATES[name])
