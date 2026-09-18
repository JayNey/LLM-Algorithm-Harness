"""
Real-provider online verification (issue #11).

These tests hit the live SiliconFlow API and are explicitly marked
``online``. Without credentials they skip automatically so CI and local
mock runs never confuse mocked success with real API verification.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from src.harness import AlgorithmHarness
from src.llm_client import LLMClient
from src.models import HarnessConfig, LLMConfig, SandboxConfig, StrategyConfig

pytestmark = pytest.mark.online

if not os.environ.get("SILICONFLOW_API_KEY"):
    pytest.skip(
        "SILICONFLOW_API_KEY not set - skipping real API verification",
        allow_module_level=True,
    )

# Preferred small models in order; the first one present in the live listing
# is used. Model size metadata is not reliably provided and stays "unknown".
PREFERRED_SMALL_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "THUDM/glm-4-9b-chat",
    "Qwen/Qwen2.5-1.5B-Instruct",
]


def _pick_small_model(client: LLMClient) -> str:
    available = set(client.list_models())
    for model_id in PREFERRED_SMALL_MODELS:
        if model_id in available:
            return model_id
    pytest.skip(f"none of the preferred small models available: {sorted(available)[:5]}...")


def test_siliconflow_single_problem_end_to_end(tmp_path):
    """Single-problem generate -> execute -> save with a real small model."""
    client = LLMClient(
        LLMConfig(
            provider="siliconflow",
            api_key="env:SILICONFLOW_API_KEY",
            model="placeholder",
            timeout=60,
        )
    )
    model_id = _pick_small_model(client)
    client.config.model = model_id

    config = HarnessConfig(
        dataset_path="data/problems.json",
        output_dir=str(tmp_path / "results"),
        llm_config=client.config,
        sandbox_config=SandboxConfig(),
        strategies=[StrategyConfig(name="vanilla", max_iterations=1)],
        problem_filters={"limit": 1},
    )

    harness = AlgorithmHarness(config)
    reports = harness.run()

    assert harness.results["vanilla"], "expected a terminal record for the problem"
    result = harness.results["vanilla"][0]
    record = {
        "verified_at": datetime.now().isoformat(),
        "model_id": model_id,
        "problem_id": result.problem_id,
        "status": result.status,
        "failure_category": result.failure_category,
        "total_tokens": result.total_tokens,
    }
    (Path(tmp_path) / "online_verification.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nONLINE VERIFICATION: {json.dumps(record, ensure_ascii=False)}")

    assert result.status == "success", (
        f"model {model_id} failed the single-problem check: {record}"
    )
