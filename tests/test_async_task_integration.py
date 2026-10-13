"""Real end-to-end integration tests for the asynchronous task queue (issue #149).

Unlike the unit tests (which patch ``celery_app.send_task`` / ``AsyncResult``),
these exercise the actual machinery:

    enqueue on a real broker  ->  a real Celery worker subprocess consumes
    ->  ``run_evaluation_task`` executes on the worker  ->  status is written
    back to the shared business DB  ->  the caller polls the task until done.

They require a reachable Redis broker. Start one with:

    docker compose up -d redis

If the broker is not reachable every test in this module is skipped, so a
normal ``pytest`` run without Redis is unaffected.

Run only these:

    pytest tests/test_async_task_integration.py -m integration -o addopts=
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

# Point Celery at a dedicated Redis virtual host BEFORE importing anything that
# reads settings, but never clobber an explicit override from the environment.
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/15")

import redis  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from api.db.engine import make_engine, make_session_factory  # noqa: E402
from api.db.models import AsyncTask, Base, Evaluation, utcnow  # noqa: E402
from src.celery_app import celery_app  # noqa: E402

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
BROKER_URL = os.environ["CELERY_BROKER_URL"]
BACKEND_URL = os.environ["CELERY_RESULT_BACKEND"]

# The evaluation Celery task writes its TaskService checkpoint tree here.
TASK_SERVICE_ROOT = REPO_ROOT / "data" / "tasks"


def _broker_available() -> bool:
    try:
        return bool(redis.Redis.from_url(BROKER_URL, socket_connect_timeout=1).ping())
    except Exception:
        return False


@pytest.fixture(scope="module")
def require_broker() -> None:
    if not _broker_available():
        pytest.skip(
            f"Redis broker not reachable at {BROKER_URL}; "
            "start it with `docker compose up -d redis`"
        )


@pytest.fixture
def db(tmp_path, require_broker) -> SimpleNamespace:
    """Create an isolated file-backed business DB shared with the worker."""
    url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    yield SimpleNamespace(url=url, engine=engine, session_factory=make_session_factory(engine))
    engine.dispose()


@pytest.fixture
def celery_worker(db, require_broker):
    """Boot a real Celery worker as a subprocess pointed at the shared DB."""
    log_path = Path(db.url.removeprefix("sqlite:///")).parent / "worker.log"
    log_file = log_path.open("w", encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), os.environ.get("PYTHONPATH", "")]).strip(
            os.pathsep
        ),
        "DATABASE_URL": db.url,
        "CELERY_BROKER_URL": BROKER_URL,
        "CELERY_RESULT_BACKEND": BACKEND_URL,
        "PYTHONUTF8": "1",
    }
    # Use the ``solo`` pool by default: it runs the real task in the worker
    # process without forking children, which is both deterministic and works
    # in sandboxes/CI where prefork setpriority is denied. Override with
    # CELERY_TEST_POOL=prefork to exercise multiprocess consumption.
    pool = os.environ.get("CELERY_TEST_POOL", "solo")
    pool_args = ["--pool", pool] + ([] if pool == "solo" else ["--concurrency", "2"])
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "src.celery_app",
            "worker",
            "--loglevel=info",
            *pool_args,
            "-Q",
            "default,evaluations",
            "--hostname=e2e@%h",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_worker(proc, log_path)
        yield proc
    finally:
        _terminate(proc)
        log_file.close()


def _wait_for_worker(proc: subprocess.Popen, log_path: Path, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"worker exited during startup:\n{log_path.read_text()}")
        try:
            text = log_path.read_text()
        except OSError:
            text = ""
        if "ready." in text:
            return
        time.sleep(0.25)
    raise RuntimeError(f"worker did not become ready in {timeout}s:\n{log_path.read_text()}")


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)  # warm shutdown
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)


def _seed_evaluation(session: Session, user_id: str, problem_count: int) -> tuple[str, str]:
    """Insert a linked Evaluation + AsyncTask pair and return (eval_id, task_id)."""
    eval_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    session.add(
        AsyncTask(
            id=task_id,
            celery_task_id="",  # filled once the message is accepted by the broker
            task_type="evaluation",
            entity_id=eval_id,
            user_id=user_id,
            status="pending",
        )
    )
    session.add(
        Evaluation(
            id=eval_id,
            user_id=user_id,
            status="pending",
            strategy_names=["vanilla"],
            problem_ids=[f"p{i}" for i in range(problem_count)],
            problem_count=problem_count,
            spent_usd=0.0,
            completed_count=0,
            failed_count=0,
            async_task_id=task_id,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    session.commit()
    return eval_id, task_id


def _poll_status(session_factory, task_id: str, target: set[str], timeout: float):
    deadline = time.monotonic() + timeout
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        with session_factory() as session:
            task = session.get(AsyncTask, task_id)
            if task is not None:
                last = {"status": task.status, "started": task.started_at, "done": task.completed_at}
                if task.status in target:
                    return task, session
        time.sleep(0.2)
    with session_factory() as session:
        raise AssertionError(f"task did not reach {target} within {timeout}s, last={last}")


class TestAsyncTaskQueueEndToEnd:
    """Real broker + worker round-trips for the task queue."""

    def test_run_evaluation_task_completes(self, db, celery_worker):
        user_id = f"e2e-{uuid.uuid4().hex[:8]}"
        with db.session_factory() as session:
            eval_id, task_id = _seed_evaluation(session, user_id, problem_count=3)

        # Enqueue onto the real broker; the running worker must pick it up.
        result = celery_app.send_task(
            "src.tasks.evaluation.run_evaluation_task", args=[eval_id], queue="evaluations"
        )
        with db.session_factory() as session:
            task = session.get(AsyncTask, task_id)
            task.celery_task_id = result.id
            session.commit()

        try:
            task, session = _poll_status(db.session_factory, task_id, {"completed"}, timeout=60)
            assert task.started_at is not None, "worker never marked the task started"
            assert task.completed_at is not None, "worker never marked the task completed"

            evaluation = session.get(Evaluation, eval_id)
            assert evaluation is not None
            assert evaluation.status == "completed"
            # The mock executor runs the full 1 strategy x 3 problems grid.
            assert evaluation.completed_count == 3
        finally:
            import shutil

            shutil.rmtree(TASK_SERVICE_ROOT / eval_id, ignore_errors=True)

    def test_cancel_pending_task_revokes_on_broker(self, db):
        user_id = f"e2e-{uuid.uuid4().hex[:8]}"
        with db.session_factory() as session:
            eval_id, task_id = _seed_evaluation(session, user_id, problem_count=2)

        # Route to a queue no worker consumes so the task stays pending, then
        # cancel it through the manager (which calls celery.control.revoke).
        result = celery_app.send_task(
            "src.tasks.evaluation.run_evaluation_task", args=[eval_id], queue="onhold"
        )
        with db.session_factory() as session:
            task = session.get(AsyncTask, task_id)
            task.celery_task_id = result.id
            session.commit()

        from src.task_manager import TaskManager

        with db.session_factory() as session:
            manager = TaskManager(session)
            cancelled = manager.cancel_task(task_id, user_id)
            assert cancelled.status == "cancelled"
            assert cancelled.completed_at is not None

        # The worker is not listening on "onhold", so nothing may run afterwards.
        time.sleep(1.0)
        with db.session_factory() as session:
            reloaded = session.get(AsyncTask, task_id)
            assert reloaded is not None
            assert reloaded.status == "cancelled"
