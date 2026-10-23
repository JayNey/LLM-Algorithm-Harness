"""Opt-in actual Docker validation; only remove the two containers created here."""

import hashlib
import json
import os
import subprocess
import uuid

import pytest

from api.monitoring.config import MonitorSettings
from api.monitoring.containers import ContainerProbes, collect_containers
from src.models import SandboxConfig
from src.sandbox_executor import SandboxExecutor
from src.utils.process_manager import run_bounded


@pytest.mark.skipif(
    os.getenv("MONITOR_CONTAINER_TESTS") != "1", reason="Explicit Docker opt-in required"
)
def test_real_docker_labeled_resources_exclude_unlabeled_container(tmp_path):
    tmp_path.chmod(0o755)
    runner = tmp_path / "runner.py"
    runner.write_text("import time\ntime.sleep(40)\n", encoding="utf-8")
    runner.chmod(0o644)
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    identities = []
    names = []
    probe = ContainerProbes(
        MonitorSettings(
            _env_file=None,
            MONITOR_CONTAINER_PROBES_ENABLED=True,
            MONITOR_CONTAINER_TIMEOUT_SECONDS=10,
            MONITOR_CONTAINER_MAX_ITEMS=64,
        )
    )
    try:
        for labeled in (True, False):
            name = "harness-resource-test-" + uuid.uuid4().hex
            names.append(name)
            command = executor._build_docker_command(str(tmp_path), str(runner), name)
            command.insert(2, "--detach")
            if not labeled:
                index = command.index("--label")
                del command[index : index + 2]
            created = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8", timeout=15, check=True
            )
            identities.append(created.stdout.strip())
        data = probe.read()
        public = [
            "container-" + hashlib.sha256(value.encode()).hexdigest()[:24] for value in identities
        ]
        rows = {row["container_id"]: row for row in data["containers"]}
        assert public[0] in rows and public[1] not in rows
        measured = rows[public[0]]
        assert measured["status"] == "ok"
        assert measured["memory_usage_bytes"] > 0
        assert measured["memory_limit_bytes"] == 256 * 1024**2
        assert measured["cpu_percent"] >= 0 and measured["pids"] >= 1
        assert probe.read()["cached"] is True
        assert all(value not in json.dumps(data) for value in identities + names)
        # Both are still running: the probe must not perform lifecycle operations.
        for identity in identities:
            running = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", identity],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
                check=True,
            )
            assert running.stdout.strip() == "true"

        def finish_our_sandbox(command, **kwargs):
            if command[1] == "stats":
                subprocess.run(
                    ["docker", "rm", "--force", names[0]],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
            return run_bounded(command, **kwargs)

        churn_probe = ContainerProbes(
            probe.settings,
            collector=lambda t, n: collect_containers(t, n, runner=finish_our_sandbox),
        )
        try:
            churn = churn_probe.read()
            assert churn["status"] == "partial" and churn["reason"] == "stats_failed"
            assert churn["listed_count"] >= 1
            vanished = next(row for row in churn["containers"] if row["container_id"] == public[0])
            assert vanished["cpu_percent"] is None
        finally:
            churn_probe.close()
        print(
            json.dumps(
                {
                    "layer": "actual Docker, isolated test containers",
                    "observation": data,
                    "sandbox_removed_between_ps_and_stats": churn,
                }
            )
        )
    finally:
        probe.close()
        for name in names:
            subprocess.run(
                ["docker", "rm", "--force", name], capture_output=True, timeout=10, check=False
            )
