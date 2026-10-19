"""Opt-in checks against an isolated Redis and an already running worker.

Set MONITOR_QUEUE_TEST_BROKER to the isolated deployment's Redis URL. No
business tasks are submitted, no databases are flushed, no LLMs are called.
"""

import json
import os

import pytest

from api.monitoring.config import MonitorSettings
from api.monitoring.queue_health import QueueProbes

pytestmark = pytest.mark.integration


def test_real_redis_and_worker_observation():
    broker = os.environ.get("MONITOR_QUEUE_TEST_BROKER")
    if not broker:
        pytest.skip("Set MONITOR_QUEUE_TEST_BROKER for isolated Redis/worker verification")
    queue = QueueProbes(
        MonitorSettings(
            _env_file=None, MONITOR_QUEUE_PROBES_ENABLED=True, MONITOR_QUEUE_TIMEOUT_SECONDS=5
        ),
        broker,
    )
    try:
        redis = queue.read("redis")
        workers = queue.read("workers")
        assert redis["status"] == "ok", redis
        assert redis["latency_ms"] >= 0
        assert workers["status"] == "ok", workers
        assert workers["worker_count"] >= 1
        assert workers["active"] >= 0 and workers["reserved"] >= 0
        assert workers["concurrency"] >= 1
        assert workers["cluster_complete"] is False
        assert workers["real_evaluation_available"] is None
        assert queue.read("workers")["cached"] is True
        assert broker not in json.dumps(workers)
        assert not queue._processes
    finally:
        queue.close()
