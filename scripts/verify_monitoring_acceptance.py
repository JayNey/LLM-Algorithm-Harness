"""Opt-in isolated monitoring acceptance; no business jobs or provider requests.

Requires Docker with cached redis:7-alpine and python:3.11-slim images. Private
logs stay in a new temporary directory; --output receives sanitized evidence.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import redis
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--run-live",
    action="store_true",
    required=True,
    help="Create only isolated test Redis/worker and sandbox containers",
)
parser.add_argument("--output", type=Path, required=True, help="Sanitized JSON evidence file")
args = parser.parse_args()
args.output = args.output.resolve()
OUT = Path(tempfile.mkdtemp(prefix="harness-monitor-acceptance-logs-"))
print(f"Private diagnostic logs: {OUT}", flush=True)
source = {
    "head": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip(),
    "dirty": subprocess.check_output(
        ["git", "status", "--short"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip(),
}
netenv = os.environ.copy()
netenv["PYTHONIOENCODING"] = "utf-8"
for key in ["HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"]:
    netenv.pop(key, None)


def command(argv, *, env=netenv, timeout=120, log=None, cwd=ROOT):
    r = subprocess.run(
        argv, env=env, cwd=cwd, text=True, encoding="utf-8", capture_output=True, timeout=timeout
    )
    if log:
        (OUT / log).write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(f"Command failed ({r.returncode}); see private log {log}")
    return r.stdout.strip()


run_id = uuid.uuid4().hex
name = "harness-monitor-acceptance-" + run_id
created = False
create_attempted = False
worker = None
worker_output = None
task_workspace = None
summary = {
    "source": source,
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "layer": "isolated actual Docker / Redis / Celery + in-process HTTP and temporary SQLite",
    "real_provider_requests_submitted": 0,
}
try:
    print("Running existing opt-in actual Docker resource integration", flush=True)
    docker_env = dict(netenv, MONITOR_CONTAINER_TESTS="1")
    command(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_monitoring_container_integration.py",
            "--no-cov",
            "-q",
            "-s",
            "--junitxml=" + str(OUT / "docker.xml"),
        ],
        env=docker_env,
        log="docker.log",
    )
    for line in (OUT / "docker.log").read_text(encoding="utf-8").splitlines():
        if line.startswith('{"layer":'):
            summary["docker_resources"] = json.loads(line)
            break
    assert "docker_resources" in summary
    task_workspace = tempfile.TemporaryDirectory(prefix="harness-monitor-acceptance-")
    task_dir = Path(task_workspace.name)
    create_attempted = True
    command(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--label",
            "io.llm-algorithm-harness.acceptance=" + run_id,
            "--name",
            name,
            "--memory",
            "64m",
            "--cpus",
            "0.5",
            "-p",
            "127.0.0.1::6379",
            "redis:7-alpine",
            "redis-server",
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        log="redis-create.log",
        timeout=20,
    )
    created = True
    mapping = command(["docker", "port", name, "6379/tcp"], timeout=5)
    assert mapping.startswith("127.0.0.1:")
    port = int(mapping.rsplit(":", 1)[1])
    broker = f"redis://127.0.0.1:{port}/0"
    client = redis.Redis.from_url(broker, socket_connect_timeout=1, socket_timeout=1)
    deadline = time.monotonic() + 10
    while True:
        try:
            if client.ping():
                break
        except redis.RedisError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)
    client.close()
    auth_secret = uuid.uuid4().hex + uuid.uuid4().hex
    crypto = Fernet.generate_key().decode()
    worker_env = dict(
        netenv,
        PYTHONPATH=str(ROOT),
        CELERY_BROKER_URL=broker,
        CELERY_RESULT_BACKEND=broker,
        AUTH_DATABASE_PATH=str(task_dir / "auth.sqlite3"),
        DATABASE_URL="sqlite:///" + (task_dir / "business.sqlite3").as_posix(),
        SECRET_KEY=auth_secret,
        ENCRYPTION_KEY=crypto,
        DATA_ROOT=str(task_dir / "data"),
        UPLOAD_DIR=str(task_dir / "uploads"),
        TASK_SERVICE_ROOT=str(task_dir / "tasks"),
        MONITOR_ADMIN_USER_IDS="[]",
        USER_DAILY_API_CALL_LIMIT="",
        USER_MONTHLY_API_CALL_LIMIT="",
    )
    (task_dir / "data").mkdir()
    worker_output = (OUT / "worker.log").open("w", encoding="utf-8")
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "src.celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--hostname=monitoring-acceptance@local",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "--loglevel=INFO",
        ],
        cwd=task_dir,
        env=worker_env,
        stdout=worker_output,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.monotonic() + 40
    while " ready." not in (OUT / "worker.log").read_text(encoding="utf-8"):
        if worker.poll() is not None:
            raise RuntimeError("Isolated worker exited; see private worker.log")
        if time.monotonic() > deadline:
            raise RuntimeError("Isolated worker did not become ready")
        time.sleep(0.2)
    print("Running existing Redis / worker read-only integration", flush=True)
    queue_env = dict(worker_env, MONITOR_QUEUE_TEST_BROKER=broker)
    command(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_monitoring_queue_integration.py",
            "--no-cov",
            "-q",
            "--junitxml=" + str(OUT / "queue.xml"),
        ],
        env=queue_env,
        log="queue.log",
        timeout=45,
    )
    # All settings imported below use this isolated deployment, not the user's .env.
    os.environ.update(worker_env)
    os.chdir(task_dir)
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient

    from api.auth.config import AuthSettings
    from api.files.config import FileSettings
    from api.main import create_app
    from api.monitoring.config import MonitorSettings
    from src.models import SandboxConfig
    from src.sandbox_executor import SandboxExecutor

    config = SandboxConfig(backend="docker", docker_image="python:3.11-slim", timeout_seconds=5)
    cli_ok, _ = SandboxExecutor(config).health_check()
    assert cli_ok
    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY=auth_secret,
        ENCRYPTION_KEY=crypto,
        AUTH_DATABASE_PATH=task_dir / "http-auth.sqlite3",
        AUTH_RATE_LIMIT=1000,
        AUTH_PROTECTED_RATE_LIMIT=10000,
    )
    files = FileSettings(_env_file=None, UPLOAD_DIR=task_dir / "http-uploads")
    monitor = MonitorSettings(
        _env_file=None,
        MONITOR_QUEUE_PROBES_ENABLED=True,
        MONITOR_QUEUE_TIMEOUT_SECONDS=5,
        MONITOR_CONTAINER_PROBES_ENABLED=True,
        MONITOR_CONTAINER_TIMEOUT_SECONDS=10,
    )
    app = create_app(auth, files, monitor_settings=monitor)
    password = "Audit-password-" + uuid.uuid4().hex + "!"
    with TestClient(app) as http:
        signup = http.post(
            "/api/v1/auth/register",
            json={
                "username": "audit_operator",
                "email": "audit@example.org",
                "password": password,
            },
        )
        assert signup.status_code == 201
        logged = http.post(
            "/api/v1/auth/login", json={"username": "audit_operator", "password": password}
        )
        assert logged.status_code == 200
        token = logged.json()["data"]["access_token"]
        http.cookies.clear()
        admin_id = app.state.auth.store.find_user("audit_operator")["id"]
        monitor.MONITOR_ADMIN_USER_IDS = [uuid.UUID(admin_id)]
        headers = {"Authorization": "Bearer " + token}

        def get(path):
            response = http.get("/api/v1" + path, headers=headers)
            assert response.status_code == 200, (path, response.status_code)
            for secret in [auth_secret, crypto, password, token]:
                assert secret not in response.text
            return response.json()["data"]

        public = http.get("/api/v1/health").json()["data"]
        assert public["scope"] == "api_liveness_only"
        sandbox = get("/health/sandbox")
        assert sandbox["status"] == "ok" and sandbox["backend"] == "docker"
        assert get("/health/sandbox")["cached"] is True
        health = get("/system/health?include_sandbox=true")
        assert health["status"] == "healthy" and health["pending_issues"] == []
        status = get("/system/status")
        assert status["workers"]["worker_count"] >= 1
        assert status["queue_metrics"]["broker_queue"]["status"] == "ok"
        assert status["queue_metrics"]["broker_queue"]["waiting"] == 0
        resources = get("/system/resources")
        assert resources["status"] == "ok"
        performance = get("/metrics/performance")
        assert len(performance["database_queries"]["sources"]) >= 2
        assert get("/system/config")["scope"] == "api_process"
        quotas = get("/quotas")
        assert quotas["evaluation_concurrency"]["used"] == 0
        assert quotas["daily_api_calls"]["used"] == 0 and quotas["monthly_api_calls"]["used"] == 0
        summary["http"] = {
            "public_health_scope": public["scope"],
            "deep_health": health,
            "sandbox_executor_ok": cli_ok,
            "sandbox_http": sandbox,
            "resource_components": {
                key: resources[key]["status"] for key in ["cpu", "memory", "disk", "file_storage"]
            },
            "broker_queue": status["queue_metrics"]["broker_queue"],
            "workers": {
                key: status["workers"][key]
                for key in [
                    "status",
                    "worker_count",
                    "active",
                    "reserved",
                    "concurrency",
                    "cluster_complete",
                ]
            },
            "task_sources": {
                key: status[key]
                for key in [
                    "task_source",
                    "task_status",
                    "task_count",
                    "async_task_source",
                    "async_task_status",
                    "async_task_count",
                ]
            },
            "database_query_sources": [
                item["source_id"] for item in performance["database_queries"]["sources"]
            ],
            "quota_observation": {
                key: quotas[key]
                for key in ["evaluation_concurrency", "daily_api_calls", "monthly_api_calls"]
            },
        }
    summary["result"] = "passed"
    print("Probe assertions passed; cleaning isolated resources", flush=True)
finally:
    os.chdir(ROOT)
    cleanup_errors = []
    if worker and worker.poll() is None:
        try:
            if os.name == "posix":
                os.killpg(worker.pid, signal.SIGTERM)
            else:
                worker.terminate()
            try:
                worker.wait(timeout=15)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(worker.pid, signal.SIGKILL)
                else:
                    worker.kill()
                worker.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            cleanup_errors.append("isolated_worker_cleanup_failed")
    if worker_output:
        worker_output.close()
    redis_removed = not create_attempted
    if create_attempted:
        try:
            # A timed-out create can still have succeeded. Verify our private
            # label before removing a generated name, never inspect other names.
            owned = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{ index .Config.Labels "io.llm-algorithm-harness.acceptance" }}',
                    name,
                ],
                env=netenv,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=5,
            )
            if owned.returncode == 0:
                if owned.stdout.strip() != run_id:
                    cleanup_errors.append("isolated_redis_ownership_mismatch")
                else:
                    subprocess.run(
                        ["docker", "rm", "--force", name],
                        env=netenv,
                        capture_output=True,
                        timeout=15,
                        check=True,
                    )
                    redis_removed = True
            elif not created:
                # No container was confirmed created; a failed inspect does not
                # prove absence when the Docker daemon is unavailable.
                cleanup_errors.append("isolated_redis_cleanup_not_verified")
            else:
                cleanup_errors.append("isolated_redis_cleanup_failed")
        except (OSError, subprocess.SubprocessError):
            cleanup_errors.append("isolated_redis_cleanup_failed")
    storage_removed = task_workspace is None
    if task_workspace is not None:
        try:
            task_workspace.cleanup()
            storage_removed = True
        except OSError:
            cleanup_errors.append("isolated_storage_cleanup_failed")
    summary["cleanup"] = {
        "isolated_worker_stopped": worker is None or worker.poll() is not None,
        "isolated_redis_removed": redis_removed,
        "isolated_storage_removed": storage_removed,
        "scope": "only resources created by this run",
        "errors": cleanup_errors,
    }
    if cleanup_errors or summary.get("result") != "passed":
        summary["result"] = "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if cleanup_errors:
        raise RuntimeError("Isolated resource cleanup was not verified; see sanitized evidence")

if summary["result"] == "passed":
    print("Monitoring acceptance passed; isolated resources cleaned", flush=True)
