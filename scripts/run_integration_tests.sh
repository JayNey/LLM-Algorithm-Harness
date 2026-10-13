#!/bin/bash
# Run the real async-task-queue integration tests (issue #149).
#
# Brings up Redis with docker compose, boots a Celery worker inside the test
# (as a subprocess), runs the @integration tests, then stops Redis again.
#
# Set KEEP_REDIS=1 to leave the redis container running after the tests.
set -euo pipefail

cd "$(dirname "$0")/.."

# Use a dedicated Redis virtual host so the tests never touch app data.
export CELERY_BROKER_URL="${CELERY_BROKER_URL:-redis://localhost:6379/15}"
export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://localhost:6379/15}"

STARTED_REDIS=0
cleanup() {
    if [[ "$STARTED_REDIS" == "1" && "${KEEP_REDIS:-0}" != "1" ]]; then
        docker compose stop redis >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

echo "==> Starting Redis (docker compose)…"
docker compose up -d redis
STARTED_REDIS=1

echo "==> Waiting for Redis to accept connections…"
for _ in $(seq 1 30); do
    if docker run --rm --network host redis:7-alpine redis-cli -n 15 ping >/dev/null 2>&1 \
        || redis-cli ping >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "==> Running integration tests…"
# -o addopts= drops the project's global --cov gate so the focused run isn't
# penalised for coverage of the rest of the suite.
python3 -m pytest tests/test_async_task_integration.py -m integration -o addopts= "$@"

echo "==> Integration tests passed."
