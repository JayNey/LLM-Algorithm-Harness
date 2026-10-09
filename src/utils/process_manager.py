"""Cross-platform process-tree management for sandboxed execution.

POSIX spawns children in a new session and terminates the tree with
``killpg``; Windows assigns children to a Job Object flagged with
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and terminates the tree with
``TerminateJobObject`` (so a leader that already exited still takes its
children down). ``run_bounded`` pumps stdout/stderr with daemon threads
(Windows ``select`` cannot poll pipes — WinError 10038), feeds stdin on
its own thread, and enforces a combined output cap and a deadline.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import IO

from src.utils.logging import get_logger

logger = get_logger(__name__)

_IS_POSIX = os.name == "posix"
_IS_WINDOWS = os.name == "nt"

_POLL_INTERVAL_SECONDS = 0.02
_READ_CHUNK_BYTES = 65536
_THREAD_JOIN_TIMEOUT_SECONDS = 5.0

# Kernel job handles are swapped out under this lock so a pump thread and
# the collecting caller never race a CloseHandle against a live handle.
_job_lock = threading.Lock()


class ProcessTimeoutError(Exception):
    """The bounded run exceeded its deadline.

    Carries whatever output was already read before termination.
    """

    def __init__(self, message: str, stdout: bytes = b"", stderr: bytes = b""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class OutputLimitExceededError(Exception):
    """The bounded run exceeded the combined output byte cap.

    Carries whatever output was already read before termination.
    """

    def __init__(self, message: str, stdout: bytes = b"", stderr: bytes = b""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


@dataclass
class BoundedRunResult:
    """Outcome of a bounded child run; streams are raw bytes."""

    returncode: int
    stdout: bytes
    stderr: bytes


if _IS_WINDOWS:
    import ctypes

    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

    _kernel32 = getattr(ctypes, "windll").kernel32
    _kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    _kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    _kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


def _assign_windows_job(process: subprocess.Popen) -> None:
    """Put the child (and its future tree) into a kill-on-close Job Object."""
    job = None
    try:
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSError("CreateJobObjectW failed")
        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            job,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            raise OSError("SetInformationJobObject failed")
        handle = int(getattr(process, "_handle"))
        if not _kernel32.AssignProcessToJobObject(job, handle):
            raise OSError("AssignProcessToJobObject failed")
        with _job_lock:
            setattr(process, "_sandbox_job", job)
            job = None
    except OSError as exc:
        if job is not None:
            _kernel32.CloseHandle(job)  # KILL_ON_JOB_CLOSE would linger otherwise
        logger.warning("job_object_assignment_failed", error=str(exc))


def spawn(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    pipe_stdin: bool = False,
) -> subprocess.Popen:
    """Start a child whose whole tree can later be terminated."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE if pipe_stdin else None,
        env=env,
        cwd=cwd,
        start_new_session=_IS_POSIX,
    )
    if _IS_WINDOWS:
        _assign_windows_job(process)
    return process


def terminate_tree(process: subprocess.Popen) -> None:
    """Kill the child and its whole tree; idempotent and never raises."""
    job = None
    with _job_lock:
        job = getattr(process, "_sandbox_job", None)
        if job is not None:
            setattr(process, "_sandbox_job", None)
    if job is not None:
        _kernel32.TerminateJobObject(job, 1)
        _kernel32.CloseHandle(job)
    elif _IS_POSIX:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def _pump(
    name: str,
    stream: IO[bytes],
    buffers: dict[str, bytearray],
    state_lock: threading.Lock,
    process: subprocess.Popen,
    limit_hit: threading.Event,
    max_output_bytes: int,
) -> None:
    while True:
        try:
            chunk = stream.read(_READ_CHUNK_BYTES)
        except (OSError, ValueError):
            return
        if not chunk:
            return
        with state_lock:
            buffers[name].extend(chunk)
            total = len(buffers["stdout"]) + len(buffers["stderr"])
        if total > max_output_bytes:
            limit_hit.set()
            terminate_tree(process)
            return


def _feed_stdin(stream: IO[bytes], input_data: bytes) -> threading.Thread:
    def feed() -> None:
        try:
            stream.write(input_data)
            stream.flush()
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    return threading.Thread(target=feed, name="feed-stdin", daemon=True)


def run_bounded(
    command: list[str],
    *,
    timeout: float,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    input_data: bytes | None = None,
    max_output_bytes: int,
) -> BoundedRunResult:
    """Run a child with a combined-output cap and a hard deadline.

    On timeout or cap breach the process tree is terminated and the
    matching error carries the output read so far.
    """
    process = spawn(command, env=env, cwd=cwd, pipe_stdin=input_data is not None)
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    state_lock = threading.Lock()
    limit_hit = threading.Event()
    deadline = time.monotonic() + timeout

    def snapshot() -> tuple[bytes, bytes]:
        with state_lock:
            return bytes(buffers["stdout"]), bytes(buffers["stderr"])

    def raise_if_limited() -> None:
        if limit_hit.is_set():
            stdout, stderr = snapshot()
            raise OutputLimitExceededError(
                f"Sandbox output exceeded {max_output_bytes} bytes", stdout, stderr
            )

    threads = [
        threading.Thread(
            target=_pump,
            args=(
                "stdout",
                process.stdout,
                buffers,
                state_lock,
                process,
                limit_hit,
                max_output_bytes,
            ),
            daemon=True,
        ),
        threading.Thread(
            target=_pump,
            args=(
                "stderr",
                process.stderr,
                buffers,
                state_lock,
                process,
                limit_hit,
                max_output_bytes,
            ),
            daemon=True,
        ),
    ]
    if input_data is not None and process.stdin is not None:
        threads.append(_feed_stdin(process.stdin, input_data))
    try:
        for thread in threads:
            thread.start()
        # The run is complete only when the child exited AND the output
        # pumps hit EOF — a grandchild holding the pipes keeps the run
        # alive until the deadline (matching the selectors semantics).
        pump_threads = threads[:2]
        while True:
            raise_if_limited()
            if time.monotonic() >= deadline:
                stdout, stderr = snapshot()
                raise ProcessTimeoutError(f"Sandbox timeout exceeded ({timeout}s)", stdout, stderr)
            if process.poll() is not None and not any(thread.is_alive() for thread in pump_threads):
                break
            time.sleep(_POLL_INTERVAL_SECONDS)
        for thread in threads:
            thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
        stdout, stderr = snapshot()
        returncode = process.returncode
        if returncode is None:  # pragma: no cover - exit settled during join
            returncode = process.wait(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
        raise_if_limited()
        return BoundedRunResult(returncode=returncode, stdout=stdout, stderr=stderr)
    finally:
        terminate_tree(process)
        for thread in threads:
            thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
