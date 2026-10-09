"""Cross-platform process-tree tests for src.utils.process_manager (issue #137).

No platform skips: the Job Object path runs on real Windows CI, the
killpg path everywhere else. Grandchild-liveness assertions use a
platform-appropriate probe.
"""

import os
import sys
import time

import pytest

from src.utils import process_manager as pm

_GRANDCHILD_SCRIPT = (
    "import subprocess, sys, time; "
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
    "print(child.pid, flush=True); "
    "time.sleep(30)"
)

_LEADER_EXITS_SCRIPT = (
    "import subprocess, sys; "
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
    "print(child.pid, flush=True); "
    "sys.exit(0)"
)


def _pid_alive(pid: int) -> bool:
    if os.name == "posix":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
    import ctypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = getattr(ctypes, "windll").kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    exit_code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel32.CloseHandle(handle)
    return exit_code.value == still_active


def _read_grandchild_pid(process) -> int:
    assert process.stdout is not None
    line = process.stdout.readline()
    return int(line.strip())


def test_terminate_tree_kills_grandchild():
    process = pm.spawn([sys.executable, "-c", _GRANDCHILD_SCRIPT])
    try:
        grandchild_pid = _read_grandchild_pid(process)
        assert _pid_alive(grandchild_pid)
        pm.terminate_tree(process)
        time.sleep(0.1)
        assert not _pid_alive(grandchild_pid)
    finally:
        pm.terminate_tree(process)


def test_terminate_tree_after_leader_exit_kills_grandchild():
    process = pm.spawn([sys.executable, "-c", _LEADER_EXITS_SCRIPT])
    try:
        grandchild_pid = _read_grandchild_pid(process)
        process.wait(timeout=10)
        time.sleep(0.1)
        assert _pid_alive(grandchild_pid), "grandchild should outlive its leader"
        pm.terminate_tree(process)
        time.sleep(0.1)
        assert not _pid_alive(grandchild_pid)
    finally:
        pm.terminate_tree(process)


def test_terminate_tree_is_idempotent():
    process = pm.spawn([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        pm.terminate_tree(process)
        pm.terminate_tree(process)
    finally:
        pm.terminate_tree(process)
    process.wait(timeout=10)


def test_run_bounded_timeout_raises():
    with pytest.raises(pm.ProcessTimeoutError):
        pm.run_bounded(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.3,
            max_output_bytes=1_000_000,
        )


def test_run_bounded_output_limit_raises_and_preserves_output():
    with pytest.raises(pm.OutputLimitExceededError) as excinfo:
        pm.run_bounded(
            [sys.executable, "-c", "print('x' * 100000)"],
            timeout=30,
            max_output_bytes=1000,
        )
    assert b"xxxx" in excinfo.value.stdout


def test_run_bounded_feeds_stdin():
    result = pm.run_bounded(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
        timeout=30,
        input_data=b"hello stdin",
        max_output_bytes=1_000_000,
    )
    assert result.returncode == 0
    assert result.stdout == b"hello stdin"


def test_run_bounded_tolerates_broken_stdin_pipe():
    result = pm.run_bounded(
        [sys.executable, "-c", "print('done')"],
        timeout=30,
        input_data=b"x" * 1_000_000,  # child exits without reading stdin
        max_output_bytes=1_000_000,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b"done"


def test_run_bounded_normal_path():
    result = pm.run_bounded(
        [sys.executable, "-c", "print('line1'); print('line2')"],
        timeout=30,
        max_output_bytes=1_000_000,
    )
    assert result.returncode == 0
    # Windows text mode emits \r\n line endings for piped stdout.
    assert result.stdout.replace(b"\r\n", b"\n") == b"line1\nline2\n"
    assert result.stderr == b""
