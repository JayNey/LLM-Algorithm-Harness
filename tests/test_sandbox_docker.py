"""Tests for the explicit Docker sandbox backend."""

import os
import sys
import time
from types import SimpleNamespace

import pytest

from src.models import Problem, SandboxConfig, TestCase
from src.sandbox_executor import SandboxExecutionError, SandboxExecutor


def _problem(expected=3, tag="docker-sum", inputs=None):
    return Problem(
        problem_id=tag,
        title=tag,
        description="Add two numbers in an isolated backend.",
        difficulty="easy",
        tags=["math"],
        test_cases=[
            TestCase(
                input={"a": 1, "b": 2} if inputs is None else inputs,
                expected_output=expected,
            )
        ],
    )


def test_docker_backend_unavailable_is_structured(monkeypatch):
    """Unavailable Docker must not silently run code on the host."""
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr(executor, "_docker_available", lambda: False)

    result = executor.execute("def solution(a, b): return a + b", _problem())

    assert result.status == "backend_unavailable"
    assert result.all_passed is False
    assert result.test_results[0].status == "backend_unavailable"


def test_empty_execution_stage_is_not_success():
    """An empty public stage cannot be reported as a successful evaluation."""
    problem = Problem(
        problem_id="empty-public",
        title="Empty Public",
        description="A problem with only hidden evaluation cases.",
        difficulty="easy",
        public_test_cases=[],
        hidden_test_cases=[{"input": {}, "expected_output": 1}],
    )
    executor = SandboxExecutor(SandboxConfig(backend="host"))

    result = executor.execute("def solution(): return 1", problem, stage="public")

    assert result.status == "sandbox_error"
    assert result.all_passed is False


def test_docker_command_has_isolation_and_resource_flags():
    """Docker invocation disables network, privileges and unbounded resources."""
    executor = SandboxExecutor(
        SandboxConfig(
            backend="docker",
            docker_image="python:3.11-slim",
            memory_limit_mb=256,
            max_processes=8,
            max_output_bytes=4096,
        )
    )

    command = executor._build_docker_command("/tmp/workdir", "/tmp/workdir/runner.py")

    assert "--network" in command and "none" in command
    assert "--read-only" in command
    assert "--cap-drop" in command and "ALL" in command
    assert "--security-opt" in command and "no-new-privileges" in command
    assert "--memory" in command and "256m" in command
    assert "--pids-limit" in command and "8" in command
    assert "--env" in command
    assert "OPENAI_API_KEY" not in " ".join(command)


def test_host_backend_output_limit_is_structured():
    """Even the explicit test backend reports oversized output distinctly."""
    executor = SandboxExecutor(
        SandboxConfig(backend="host", max_output_bytes=1024, allowed_imports=[])
    )
    problem = Problem(
        problem_id="output-limit",
        title="Output Limit",
        description="Emit too much output.",
        difficulty="easy",
        tags=["test"],
        test_cases=[TestCase(input={}, expected_output=1)],
    )
    code = "def solution():\n    print('x' * 10000)\n    return 1\n"

    result = executor.execute(code, problem)

    assert result.status == "output_limit"
    assert result.test_results[0].status == "output_limit"


def test_docker_backend_runs_algorithm_without_host_environment(monkeypatch):
    """A successful container run receives no host API-key environment."""
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr(executor, "_docker_available", lambda: True)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="3\n", stderr="")

    monkeypatch.setattr(executor, "_run_command", fake_run)
    result = executor.execute("def solution(a, b): return a + b", _problem())

    assert result.status == "success"
    assert result.test_results[0].actual_output == 3
    command, kwargs = calls[0]
    assert "--network" in command and "none" in command
    assert kwargs["env"] == {"PATH": kwargs["env"]["PATH"]}


def test_docker_workspace_is_readable_by_non_root_container_user(monkeypatch):
    """The temporary workspace permissions allow the configured numeric user to read it."""
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr(executor, "_docker_available", lambda: True)
    modes = []

    def record_chmod(path, mode, **kwargs):
        modes.append((str(path), mode))

    monkeypatch.setattr("src.sandbox_executor.os.chmod", record_chmod)
    monkeypatch.setattr(
        executor,
        "_run_command",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="3\n", stderr=""),
    )

    result = executor.execute("def solution(a, b): return a + b", _problem())

    assert result.status == "success"
    assert {mode for _, mode in modes} >= {0o755, 0o644}


def test_timeout_terminates_the_entire_process_group(tmp_path):
    """A timeout must not leave a child process running after the parent exits."""
    pid_file = tmp_path / "child.pid"
    script = (
        "import os, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"open({str(pid_file)!r}, 'w').write(str(child.pid)); "
        "time.sleep(30)"
    )
    executor = SandboxExecutor(SandboxConfig(backend="host", timeout_seconds=1))

    with pytest.raises(SandboxExecutionError, match="timeout"):
        executor._run_command([sys.executable, "-c", script], timeout=0.2)

    child_pid = int(pid_file.read_text())
    time.sleep(0.05)
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_parent_exit_still_terminates_child_process_group(tmp_path):
    """A child cannot survive when its command leader exits early."""
    pid_file = tmp_path / "child.pid"
    script = (
        "import subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"open({str(pid_file)!r}, 'w').write(str(child.pid)); "
        "sys.exit(0)"
    )
    executor = SandboxExecutor(SandboxConfig(backend="host", timeout_seconds=1))

    with pytest.raises(SandboxExecutionError, match="timeout"):
        executor._run_command([sys.executable, "-c", script], timeout=0.2)

    child_pid = int(pid_file.read_text())
    time.sleep(0.05)
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_docker_pid_limit_error_maps_to_process_limit(monkeypatch):
    """Common Linux EAGAIN wording maps to process_limit."""
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr(executor, "_docker_available", lambda: True)
    monkeypatch.setattr(
        executor,
        "_run_command",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="BlockingIOError: [Errno 11] Resource temporarily unavailable",
        ),
    )

    result = executor.execute("def solution(a, b): return a + b", _problem())

    assert result.status == "process_limit"
    assert result.test_results[0].status == "process_limit"


@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1",
    reason="set RUN_DOCKER_TESTS=1 to run integration tests against Docker",
)
def test_real_docker_isolates_host_file_environment_and_network():
    """A real container cannot read host files, API keys, or use the network."""
    file_result = SandboxExecutor(SandboxConfig(backend="docker")).execute(
        "def solution():\n    return open('/Users/easonzhong/Desktop/算法大模型系统/LLM-Algorithm-Harness/README.md').read()",
        _problem(None, "host-file", {}),
    )
    env_result = SandboxExecutor(SandboxConfig(backend="docker", allowed_imports=["os"])).execute(
        "import os\ndef solution(): return os.environ.get('OPENAI_API_KEY')",
        _problem(None, "api-key-env", {}),
    )
    network_result = SandboxExecutor(
        SandboxConfig(backend="docker", allowed_imports=["urllib"])
    ).execute(
        "import urllib.request\ndef solution(): return urllib.request.urlopen('http://example.com', timeout=1).status",
        _problem(None, "network", {}),
    )

    assert file_result.test_results[0].status == "sandbox_error"
    assert env_result.status == "success"
    assert env_result.test_results[0].actual_output is None
    assert network_result.test_results[0].status == "sandbox_error"


@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1",
    reason="set RUN_DOCKER_TESTS=1 to run integration tests against Docker",
)
def test_real_docker_enforces_timeout_output_memory_and_process_limits():
    """A real container enforces all configured resource boundaries."""
    timeout_result = SandboxExecutor(SandboxConfig(backend="docker", timeout_seconds=1)).execute(
        "def solution():\n    while True: pass", _problem(None, "timeout", {})
    )
    output_result = SandboxExecutor(SandboxConfig(backend="docker", max_output_bytes=2048)).execute(
        "def solution():\n    print('x' * 500000)\n    return None",
        _problem(None, "output", {}),
    )
    memory_result = SandboxExecutor(SandboxConfig(backend="docker", memory_limit_mb=256)).execute(
        "def solution():\n    return len(bytearray(400 * 1024 * 1024))",
        _problem(400 * 1024 * 1024, "memory", {}),
    )
    process_result = SandboxExecutor(
        SandboxConfig(backend="docker", allowed_imports=["subprocess", "sys"])
    ).execute(
        "import subprocess, sys\ndef solution():\n    return [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']).pid for _ in range(64)]",
        _problem(None, "process", {}),
    )

    assert timeout_result.status == "timeout"
    assert output_result.status == "output_limit"
    assert memory_result.status == "memory_error"
    assert process_result.status == "process_limit"


def test_docker_oom_exit_maps_to_memory_error(monkeypatch):
    """Docker's conventional OOM exit code is exposed structurally."""
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr(executor, "_docker_available", lambda: True)
    monkeypatch.setattr(
        executor,
        "_run_command",
        lambda *args, **kwargs: SimpleNamespace(returncode=137, stdout="", stderr=""),
    )

    result = executor.execute("def solution(a, b): return a + b", _problem())

    assert result.status == "memory_error"
    assert result.test_results[0].status == "memory_error"


def test_docker_image_unavailable_is_detected(monkeypatch):
    """A running daemon is insufficient when the configured image is missing."""
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr("src.sandbox_executor.shutil.which", lambda name: "/usr/bin/docker")
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="27\n", stderr=""),
            SimpleNamespace(returncode=1, stdout="", stderr="No such image"),
        ]
    )
    monkeypatch.setattr("src.sandbox_executor.subprocess.run", lambda *a, **k: next(responses))

    assert executor._docker_available() is False


def test_docker_missing_image_run_maps_backend_unavailable(monkeypatch):
    """Docker's image-not-found exit is exposed as backend_unavailable."""
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr(executor, "_docker_available", lambda: True)
    monkeypatch.setattr(
        executor,
        "_run_command",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=125, stdout="", stderr="Unable to find image 'missing:latest'"
        ),
    )

    result = executor.execute("def solution(a, b): return a + b", _problem())

    assert result.status == "backend_unavailable"
    assert result.test_results[0].status == "backend_unavailable"


def test_host_backend_does_not_inherit_api_key_environment(monkeypatch):
    """Explicit host tests still run with a scrubbed environment."""
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-enter-sandbox")
    executor = SandboxExecutor(SandboxConfig(backend="host", allowed_imports=["os"]))
    problem = Problem(
        problem_id="env-check",
        title="Environment Check",
        description="Check scrubbed environment.",
        difficulty="easy",
        tags=["security"],
        test_cases=[TestCase(input={}, expected_output=None)],
    )

    result = executor.execute(
        "import os\ndef solution(): return os.environ.get('OPENAI_API_KEY')",
        problem,
    )

    assert result.status == "success"
    assert result.test_results[0].actual_output is None
