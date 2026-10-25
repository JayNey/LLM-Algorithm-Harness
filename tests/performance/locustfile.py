"""Authenticated read load. See README.md for profiles and isolated target setup."""

import math
import os
from pathlib import Path

from locust import HttpUser, LoadTestShape, between, events, task
from locust.exception import StopUser

PROFILE = os.getenv("PERF_PROFILE", "load")
if PROFILE not in {"load", "stress", "concurrency"}:
    raise ValueError("PERF_PROFILE must be load, stress or concurrency")
USERS = int(os.getenv("PERF_USERS", "10"))
STAGE_SECONDS = float(os.getenv("PERF_STAGE_SECONDS", "60"))
MAX_P95 = float(os.getenv("PERF_MAX_P95_MS", "1000"))
if USERS < 1 or not all(math.isfinite(v) and v > 0 for v in (STAGE_SECONDS, MAX_P95)):
    raise ValueError("users, stage seconds and p95 threshold must be finite and positive")


class ApiUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        token = os.getenv("PERF_TOKEN")
        if not token and os.getenv("PERF_TOKEN_FILE"):
            token = Path(os.environ["PERF_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
        if not token:
            raise StopUser("PERF_TOKEN or PERF_TOKEN_FILE is required")
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    def read(self, path, paginated=False):
        with self.client.get(path, name=path, catch_response=True, timeout=10) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            try:
                data = response.json()
                valid = data.get("success") is True and isinstance(data.get("data"), dict)
                if paginated:
                    valid = (
                        valid
                        and isinstance(data["data"].get("items"), list)
                        and isinstance(data["data"].get("total"), int)
                    )
                if not valid:
                    response.failure("invalid response envelope")
            except (ValueError, TypeError, AttributeError):
                response.failure("invalid JSON response")

    @task(1)
    def health(self):
        self.read("/api/v1/health")

    @task(3)
    def evaluations(self):
        self.read("/api/v1/evaluations?limit=20", paginated=True)

    @task(2)
    def task_list(self):
        self.read("/api/v1/tasks?limit=20", paginated=True)


class ApiShape(LoadTestShape):
    """Load: steady; stress: 1x/2x/4x/8x; concurrency: immediate burst."""

    def tick(self):
        stage = int(self.get_run_time() // STAGE_SECONDS)
        if stage >= (4 if PROFILE == "stress" else 1):
            return None
        users = USERS * (2**stage if PROFILE == "stress" else 1)
        return users, users if PROFILE == "concurrency" else max(1, users / 5)


@events.quitting.add_listener
def check_results(environment, **kwargs):
    stats = environment.stats.total
    if (
        stats.num_requests == 0
        or stats.num_failures
        or (stats.get_response_time_percentile(0.95) or 0) > MAX_P95
    ):
        environment.process_exit_code = 1
