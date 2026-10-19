"""Code capability is distinct from provider, credentials and sandbox readiness."""

from typing import Any


def evaluation_capability() -> dict[str, Any]:
    return {
        "evaluation_worker_implementation": "algorithm_harness",
        "real_evaluation_available": None,
        "execution_readiness": "not_checked",
    }
