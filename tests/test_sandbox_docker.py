"""Tests for the explicit Docker sandbox backend."""

import ast
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_process_manager import _pid_alive

from src.models import Problem, SandboxConfig, TestCase
from src.sandbox_executor import FUNCTION_RESULT_MARKER, SandboxExecutionError, SandboxExecutor


def _successful_function_run(command, **kwargs):
    """Model the result channel emitted by the current container wrapper."""
    mount = command[command.index("--mount") + 1]
    workdir = next(part[4:] for part in mount.split(",") if part.startswith("src="))
    wrapper = Path(workdir, "runner.py").read_text(encoding="utf-8")
    marker = next(
        node.value
        for node in ast.walk(ast.parse(wrapper))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith(FUNCTION_RESULT_MARKER + ":")
    )
    return SimpleNamespace(returncode=0, stdout="debug\n", stderr=marker + "3\n")


@pytest.fixture(autouse=True)
def _stub_docker_cleanup(monkeypatch, request):
    """Unit tests must not wait on a real Docker daemon to remove containers."""
    if request.node.name.startswith("test_real_docker"):
        return

    def fake_run(command, *args, **kwargs):
        if isinstance(command, (list, tuple)) and list(command[:2]) == ["docker", "rm"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.run(command, *args, **kwargs)

    monkeypatch.setattr("src.sandbox_executor.subprocess.run", fake_run)


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
    assert "--label" in command
    assert "io.llm-algorithm-harness.sandbox=v1" in command


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
        return _successful_function_run(command, **kwargs)

    monkeypatch.setattr(executor, "_run_command", fake_run)
    result = executor.execute("def solution(a, b): return a + b", _problem())

    assert result.status == "success"
    assert result.test_results[0].actual_output == 3
    command, kwargs = calls[0]
    assert "--network" in command and "none" in command
    assert kwargs["env"] == {"PATH": kwargs["env"]["PATH"]}


def test_docker_function_stdout_without_marker_is_rejected(monkeypatch):
    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr(executor, "_docker_available", lambda: True)
    monkeypatch.setattr(
        executor,
        "_run_command",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="3\n", stderr=""),
    )
    result = executor.execute(
        "def solution(a, b):\n    print(a + b)\n    raise SystemExit(0)", _problem()
    )
    assert result.all_passed is False
    assert result.test_results[0].status == "runtime_error"
    assert "marker was not produced" in result.test_results[0].error_message


@pytest.mark.skipif(os.getenv("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1")
@pytest.mark.parametrize(
    "code, passed",
    [
        ("def solution(a, b):\n    print(a + b)\n    raise SystemExit(0)", False),
        ("def solution(a, b):\n    return a + b", True),
        ("def solution(a, b):\n    print('debug')\n    return a + b", True),
    ],
)
def test_real_docker_function_result_channel(code, passed):
    result = SandboxExecutor(SandboxConfig(backend="docker")).execute(code, _problem())
    assert result.all_passed is passed
    if passed:
        assert result.status == "success"
        assert result.test_results[0].actual_output == 3
    else:
        assert result.test_results[0].status == "runtime_error"
        assert "marker was not produced" in result.test_results[0].error_message


@pytest.mark.skipif(os.getenv("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1")
def test_real_docker_stdin_stdout_does_not_require_function_marker():
    problem = _problem("3\n", inputs="1 2\n").model_copy(
        update={"input_output_mode": "stdin_stdout", "entry_point": "main()"}
    )
    result = SandboxExecutor(SandboxConfig(backend="docker")).execute(
        "a, b = map(int, input().split())\nprint(a + b)", problem
    )
    assert result.all_passed is True


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
        _successful_function_run,
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
        f"open({str(pid_file)!r}, 'w', encoding='utf-8').write(str(child.pid)); "
        "time.sleep(30)"
    )
    executor = SandboxExecutor(SandboxConfig(backend="host", timeout_seconds=1))

    with pytest.raises(SandboxExecutionError, match="timeout"):
        executor._run_command([sys.executable, "-c", script], timeout=0.2)

    child_pid = int(pid_file.read_text(encoding="utf-8"))
    time.sleep(0.05)
    assert not _pid_alive(child_pid)


def test_parent_exit_still_terminates_child_process_group(tmp_path):
    """A child cannot survive when its command leader exits early."""
    pid_file = tmp_path / "child.pid"
    script = (
        "import subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"open({str(pid_file)!r}, 'w', encoding='utf-8').write(str(child.pid)); "
        "sys.exit(0)"
    )
    executor = SandboxExecutor(SandboxConfig(backend="host", timeout_seconds=1))

    with pytest.raises(SandboxExecutionError, match="timeout"):
        executor._run_command([sys.executable, "-c", script], timeout=0.2)

    child_pid = int(pid_file.read_text(encoding="utf-8"))
    time.sleep(0.05)
    assert not _pid_alive(child_pid)


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


@pytest.mark.parametrize("mode", ["function", "stdin_stdout"])
@pytest.mark.parametrize(
    "entry, failure",
    [("direct", item) for item in [None, "exit", "output_limit", "timeout", "parse"]]
    + [("harness", None), ("profile", None)],
)
@pytest.mark.parametrize("cleanup_raises", [False, True])
def test_parallel_command_timing_is_owned_by_each_call(
    monkeypatch, tmp_path, mode, entry, failure, cleanup_raises
):
    """A fast call paused in cleanup must never inherit B's six-second duration."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from src.utils.process_manager import OutputLimitExceededError, ProcessTimeoutError

    executor = SandboxExecutor(SandboxConfig(backend="docker", timeout_seconds=5))
    monkeypatch.setattr(executor, "_docker_available", lambda: True)
    local = threading.local()
    a_cleaning = threading.Event()
    b_finished = threading.Event()

    def clock():
        return next(local.ticks)

    monkeypatch.setattr(
        "src.sandbox_executor.time",
        SimpleNamespace(perf_counter=clock, monotonic=time.monotonic, time=time.time),
    )

    def run(command, **kwargs):
        if local.label == "B":
            assert a_cleaning.wait(5)
        if local.label == "A":
            if failure == "output_limit":
                raise OutputLimitExceededError("too much output")
            if failure == "timeout":
                raise ProcessTimeoutError("timed out")
            if failure == "exit":
                return SimpleNamespace(returncode=1, stdout=b"", stderr=b"failed")
            if failure == "parse":
                return SimpleNamespace(returncode=0, stdout=b"not-json", stderr=b"")
        if entry == "profile":
            mount = command[command.index("--mount") + 1]
            workdir = next(part[4:] for part in mount.split(",") if part.startswith("src="))
            with subprocess.Popen(
                [sys.executable, str(Path(workdir, "runner.py"))],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as process:
                stdout, stderr = process.communicate(timeout=5)
                return SimpleNamespace(returncode=process.returncode, stdout=stdout, stderr=stderr)
        if mode == "function":
            result = _successful_function_run(command)
            return SimpleNamespace(
                returncode=0, stdout=result.stdout.encode(), stderr=result.stderr.encode()
            )
        return SimpleNamespace(returncode=0, stdout=b"3", stderr=b"")

    def cleanup(*args, **kwargs):
        if local.label == "A":
            a_cleaning.set()
            assert b_finished.wait(5)
        if cleanup_raises:
            raise RuntimeError("cleanup failed")
        return subprocess.CompletedProcess(args[0], 0)

    monkeypatch.setattr("src.sandbox_executor.run_bounded", run)
    monkeypatch.setattr("src.sandbox_executor.subprocess.run", cleanup)
    problem = _problem(3 if mode == "function" else "3", inputs={}).model_copy(
        update={"input_output_mode": mode}
    )
    if failure == "parse" and mode == "stdin_stdout":
        from src.models import JudgeConfig

        problem = problem.model_copy(update={"judge_config": JudgeConfig(output_format="json")})

    code = "def solution(): return 3" if mode == "function" else "print(3)"

    def execute(label):
        local.label = label
        local.ticks = iter([0, 0.1 if label == "A" else 6])
        try:
            if entry == "profile":
                return executor.execute_with_memory_profiling(code, problem)
            return executor._execute_single_test(code, problem.test_cases[0], 0, problem)
        finally:
            if label == "B":
                b_finished.set()

    if entry == "harness":
        import json

        from src.harness import AlgorithmHarness
        from src.models import ExecutionResult, HarnessConfig, LLMConfig, StrategyConfig

        dataset = tmp_path / "problems.json"
        dataset.write_text(
            json.dumps(
                [
                    problem.model_copy(update={"problem_id": label}).model_dump(mode="json")
                    for label in ["A", "B"]
                ]
            ),
            encoding="utf-8",
        )
        results = {}

        class Strategy:
            def execute(self, selected_problem):
                result = execute(selected_problem.problem_id)
                results[selected_problem.problem_id] = result
                return ExecutionResult(
                    problem_id=selected_problem.problem_id,
                    strategy="vanilla",
                    generated_code="",
                    status="success" if result.passed else "failed",
                )

        harness = AlgorithmHarness(
            HarnessConfig(
                dataset_path=str(dataset),
                output_dir=str(tmp_path / "results"),
                llm_config=LLMConfig(provider="openai", api_key="test-key", model="test"),
                sandbox_config=executor.config,
                strategies=[StrategyConfig(name="vanilla")],
            )
        )
        monkeypatch.setattr(
            harness, "_prepare_strategy_runtime", lambda config: (Strategy(), executor)
        )
        reports = harness.run(use_task_service=True)
        assert reports["vanilla"].solved_problems == 1
        assert harness.task_record.state == "completed"
        a_result, b_result = results["A"], results["B"]
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(execute, "A")
            b = pool.submit(execute, "B")
            a_result, b_result = a.result(timeout=10), b.result(timeout=10)
    if entry == "profile":
        assert a_result[1]["peak_bytes"] > 0
        assert b_result == {}
        return
    expected_status = {
        None: "passed",
        "exit": "sandbox_error",
        "output_limit": "output_limit",
        "timeout": "timeout",
        "parse": "runtime_error",
    }[failure]
    assert (a_result.status, a_result.execution_time) == (expected_status, 0.1)
    assert (b_result.status, b_result.execution_time) == ("timeout", 6)


@pytest.mark.skipif(os.getenv("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1")
@pytest.mark.parametrize("mode", ["function", "stdin_stdout"])
def test_real_docker_parallel_timing_excludes_cleanup(monkeypatch, mode):
    """Real containers overlap on a shared executor while fast cleanup waits for slow work."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    executor = SandboxExecutor(
        SandboxConfig(backend="docker", timeout_seconds=5, allowed_imports=["time"])
    )
    a_cleaning, b_finished = threading.Event(), threading.Event()
    local = threading.local()
    real_run = subprocess.run

    def cleanup(command, *args, **kwargs):
        if command[:2] == ["docker", "rm"] and local.label == "A":
            a_cleaning.set()
            assert b_finished.wait(20)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("src.sandbox_executor.subprocess.run", cleanup)
    problem = _problem(3 if mode == "function" else "3", inputs={}).model_copy(
        update={"input_output_mode": mode}
    )

    def execute(label):
        local.label = label
        if label == "B":
            assert a_cleaning.wait(10)
        code = "def solution(): return 3" if mode == "function" else "print(3)"
        if label == "B":
            code = "import time\ntime.sleep(6)\n" + code
        try:
            return executor._execute_single_test(code, problem.test_cases[0], 0, problem)
        finally:
            if label == "B":
                b_finished.set()

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(execute, "A"), pool.submit(execute, "B")
        fast, slow = a.result(timeout=30), b.result(timeout=30)
    assert fast.status == "passed"
    assert 0 < fast.execution_time < 5
    assert slow.status == "timeout"
    assert slow.execution_time > 5
    assert time.monotonic() - started > 5


_LEETCODE_JUDGE_CASES = [
    pytest.param(
        "73",
        "set-matrix-zeroes",
        "setZeroes",
        "matrix",
        "matrix = [[1,1,1],[1,0,1],[1,1,1]]",
        "[[1,0,1],[0,0,0],[1,0,1]]",
        "class Solution:\n"
        "    def setZeroes(self, matrix):\n"
        "        zeros = [(i, j) for i, row in enumerate(matrix)"
        " for j, value in enumerate(row) if value == 0]\n"
        "        for i, j in zeros:\n"
        "            matrix[i][:] = [0] * len(matrix[i])\n"
        "            for row in matrix:\n"
        "                row[j] = 0\n",
        id="matrix",
    ),
    pytest.param(
        "88",
        "merge-sorted-array",
        "merge",
        "nums1, m, nums2, n",
        "nums1 = [1,2,3,0,0,0], m = 3, nums2 = [2,5,6], n = 3",
        "[1,2,2,3,5,6]",
        "class Solution:\n"
        "    def merge(self, nums1, m, nums2, n):\n"
        "        nums1[:] = sorted(nums1[:m] + nums2[:n])\n",
        id="merge",
    ),
    pytest.param(
        "49",
        "group-anagrams",
        "groupAnagrams",
        "strs",
        'strs = ["eat","tea","eat","tan","nat","bat"]',
        '[["bat"],["nat","tan"],["tea","eat","eat"]]',
        "class Solution:\n"
        "    def groupAnagrams(self, strs):\n"
        "        groups = {}\n"
        "        for word in strs:\n"
        "            groups.setdefault(tuple(sorted(word)), []).append(word)\n"
        "        return list(groups.values())\n",
        id="anagrams",
    ),
]


@pytest.mark.parametrize(
    "backend",
    [
        "host",
        pytest.param(
            "docker",
            marks=pytest.mark.skipif(
                os.getenv("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1"
            ),
        ),
    ],
)
@pytest.mark.parametrize("number,slug,method,args,inputs,expected,code", _LEETCODE_JUDGE_CASES)
def test_real_docker_and_host_judge_imported_leetcode_outputs(
    backend, number, slug, method, args, inputs, expected, code
):
    from api.files.parsing import validate_problem
    from src.importers.leetcode import LeetCodeImporter
    from src.problem_loader import ProblemLoader

    [problem] = LeetCodeImporter().transform_to_schema(
        {
            "questionFrontendId": number,
            "titleSlug": slug,
            "content": f"<pre>Input: {inputs}\nOutput: {expected}</pre>",
            "codeSnippets": [
                {
                    "langSlug": "python3",
                    "code": f"class Solution:\n    def {method}(self, {args}): ...",
                }
            ],
        }
    )
    old_record = problem.model_dump(mode="json")
    old_record["judge_config"] = {
        "comparison": "float_tolerance",
        "float_tolerance": 1e-6,
        "whitespace": "trim",
        "output_format": "auto",
    }
    executor = SandboxExecutor(SandboxConfig(backend=backend))
    [cli_problem] = ProblemLoader().validate_dataset([old_record])
    web_problem = validate_problem(old_record)
    assert cli_problem == web_problem == problem
    for saved_problem in (problem, cli_problem):
        result = executor.execute(code, saved_problem)
        assert result.all_passed, result.model_dump()
    if number in {"73", "88"}:
        # A correct return value alone must not pass an in-place problem.
        return_only = f"class Solution:\n    def {method}(self, {args}): return {expected}"
        assert executor.execute(return_only, problem).test_results[0].status == "wrong_answer"
    else:
        for wrong in (
            [["eat", "tea"], ["tan", "nat"], ["bat"]],
            [["eat", "tea", "eat", "eat"], ["tan", "nat"], ["bat"]],
            [["eat", "tea", "tan"], ["eat", "nat"], ["bat"]],
        ):
            incorrect = f"class Solution:\n    def {method}(self, {args}): return {wrong!r}"
            assert executor.execute(incorrect, problem).test_results[0].status == "wrong_answer"

        ordered = problem.model_dump(mode="json")
        ordered["judge_config"] = {"comparison": "unordered"}
        result = executor.execute(code, Problem.model_validate(ordered))
        assert result.test_results[0].status == "wrong_answer"


@pytest.mark.parametrize(
    "backend",
    [
        "host",
        pytest.param(
            "docker",
            marks=pytest.mark.skipif(
                os.getenv("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1"
            ),
        ),
    ],
)
def test_real_docker_and_host_respect_declared_function_judge(backend):
    executor = SandboxExecutor(SandboxConfig(backend=backend))
    record = _problem([1, 2], inputs={"items": [2, 1]}).model_dump(mode="json")
    record["judge_config"] = {"comparison": "exact", "result_argument": "items"}
    problem = Problem.model_validate(record)
    assert executor.execute(
        "def solution(items):\n    items.sort()\n    return object()", problem
    ).all_passed

    record["judge_config"] = {"comparison": "exact"}
    problem = Problem.model_validate(record)
    assert executor.execute("def solution(items): return [1, 2]", problem).all_passed
    assert (
        executor.execute("def solution(items): return items", problem).test_results[0].status
        == "wrong_answer"
    )


def test_declared_result_argument_requires_named_input():
    record = _problem().model_dump(mode="json")
    record["judge_config"] = {"result_argument": "missing"}
    with pytest.raises(ValueError, match="result_argument"):
        Problem.model_validate(record)


_TREE_PREORDER = """
class Solution:
    def buildTree(self, preorder, inorder) -> Optional[TreeNode]:
        if not preorder:
            return None
        root = TreeNode(preorder[0])
        pivot = inorder.index(root.val)
        root.left = self.buildTree(preorder[1:pivot + 1], inorder[:pivot])
        root.right = self.buildTree(preorder[pivot + 1:], inorder[pivot + 1:])
        return root
"""

_TREE_POSTORDER = """
class Solution:
    def buildTree(self, inorder, postorder) -> Optional[TreeNode]:
        if not postorder:
            return None
        root = TreeNode(postorder[-1])
        pivot = inorder.index(root.val)
        root.left = self.buildTree(inorder[:pivot], postorder[:pivot])
        root.right = self.buildTree(inorder[pivot + 1:], postorder[pivot:-1])
        return root
"""

_CLONE_GRAPH = """
class Solution:
    def cloneGraph(self, node: Optional['Node']) -> Optional['Node']:
        copies = {}
        def visit(old):
            if old not in copies:
                copies[old] = Node(old.val)
                copies[old].neighbors = [visit(n) for n in reversed(old.neighbors)]
            return copies[old]
        return visit(node) if node is not None else None
"""

_COPY_RANDOM_LIST = """
class Solution:
    def copyRandomList(self, head: 'Optional[Node]') -> 'Optional[Node]':
        copies = {None: None}
        node = head
        while node is not None:
            copies[node] = Node(node.val)
            node = node.next
        node = head
        while node is not None:
            copies[node].next = copies[node.next]
            copies[node].random = copies[node.random]
            node = node.next
        return copies[head]
"""


def _import_node_problem(number, signature, examples):
    from src.importers.leetcode import LeetCodeImporter

    [problem] = LeetCodeImporter().transform_to_schema(
        {
            "questionFrontendId": number,
            "title": f"LeetCode {number}",
            "content": "".join(
                f"<pre>Input: {inputs}\nOutput: {expected}</pre>" for inputs, expected in examples
            ),
            "codeSnippets": [
                {"langSlug": "python3", "code": f"class Solution:\n    def {signature}: ..."}
            ],
        }
    )
    return problem


@pytest.mark.parametrize(
    "backend",
    [
        "host",
        pytest.param(
            "docker",
            marks=pytest.mark.skipif(
                os.getenv("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1"
            ),
        ),
    ],
)
@pytest.mark.parametrize(
    "number,signature,examples,correct,incorrect",
    [
        pytest.param(
            "105",
            "buildTree(self, preorder, inorder) -> Optional[TreeNode]",
            [
                ("preorder = [3,9,20,15,7], inorder = [9,3,15,20,7]", "[3,9,20,null,null,15,7]"),
                ("preorder = [], inorder = []", "[]"),
            ],
            _TREE_PREORDER,
            [
                "return TreeNode(3, TreeNode(20), TreeNode(9))",
                "root = TreeNode(3); root.left = root; return root",
                "return [3,9,20,None,None,15,7]",
            ],
            id="preorder-tree",
        ),
        pytest.param(
            "106",
            "buildTree(self, inorder, postorder) -> Optional[TreeNode]",
            [
                ("inorder = [9,3,15,20,7], postorder = [9,15,7,20,3]", "[3,9,20,null,null,15,7]"),
                ("inorder = [], postorder = []", "[]"),
            ],
            _TREE_POSTORDER,
            ["return TreeNode(3, TreeNode(9), TreeNode(20))"],
            id="postorder-tree",
        ),
        pytest.param(
            "133",
            "cloneGraph(self, node: Optional['Node']) -> Optional['Node']",
            [
                ("adjList = [[4,2],[1,3],[2,4],[1,3]]", "[[4,2],[3,1],[2,4],[1,3]]"),
                ("adjList = [[]]", "[[]]"),
                ("adjList = []", "[]"),
            ],
            _CLONE_GRAPH,
            [
                "return node",
                "return Node(node.val, node.neighbors[:])",
                "return Node(node.val)",
                "return Node(2, node.neighbors)",
                """nodes = [node, *node.neighbors, node.neighbors[0].neighbors[1]]
copies = {old: Node(old.val, old.neighbors) for old in nodes}
for old in nodes:
    old.neighbors[:] = [copies[neighbor] for neighbor in old.neighbors]
return copies[node]""",
            ],
            id="cyclic-graph",
        ),
        pytest.param(
            "138",
            "copyRandomList(self, head: 'Optional[Node]') -> 'Optional[Node]'",
            [
                ("head = [[7,null],[7,2],[11,0],[10,3]]", "[[7,null],[7,2],[11,0],[10,3]]"),
                ("head = []", "[]"),
            ],
            _COPY_RANDOM_LIST,
            [
                "return head",
                "return Node(head.val, head.next)",
                "result = Node(head.val); result.next = result; return result",
                "result = Node(head.val); result.random = head.next; return result",
                "return Node(7, Node(7, Node(11, Node(10))))",
            ],
            id="random-list",
        ),
    ],
)
def test_real_docker_and_host_judge_leetcode_nodes(
    backend, number, signature, examples, correct, incorrect
):
    from api.files.parsing import validate_problem
    from src.incremental.fingerprint import compute_problem_fingerprint
    from src.problem_loader import ProblemLoader

    problem = _import_node_problem(number, signature, examples)
    executor = SandboxExecutor(SandboxConfig(backend=backend))
    result = executor.execute(correct, problem)
    assert result.all_passed, result.model_dump()
    assert len(result.test_results) == len(examples)

    # Simulate serialized defaults from before node support, including the old adjList key.
    record = problem.model_dump(mode="json")
    record["judge_config"] = {
        "comparison": "float_tolerance",
        "result_argument": None,
        "float_tolerance": 1e-6,
        "whitespace": "trim",
        "output_format": "auto",
    }
    if number == "133":
        for case in record["public_test_cases"]:
            if "node" in case["input"]:
                case["input"]["adjList"] = case["input"].pop("node")
    [cli_problem] = ProblemLoader().validate_dataset([record])
    web_problem = validate_problem(record)
    assert cli_problem == web_problem
    assert compute_problem_fingerprint(cli_problem) == compute_problem_fingerprint(problem)
    result = executor.execute(correct, cli_problem)
    assert result.all_passed, result.model_dump()

    # Only the first, non-empty case is needed for the fixed incorrect solutions.
    first_case = problem.model_copy(update={"public_test_cases": problem.public_test_cases[:1]})
    for body in incorrect:
        indented = "\n".join(f"        {line}" for line in body.splitlines())
        code = f"class Solution:\n    def {signature}:\n{indented}"
        case = executor.execute(code, first_case).test_results[0]
        assert case.status == "wrong_answer", case.model_dump()


def test_leetcode_import_reports_unsupported_node_signature():
    problem = _import_node_problem(
        "206",
        "reverseList(self, head: Optional[ListNode]) -> Optional[ListNode]",
        [("head = [1,2]", "[2,1]")],
    )
    assert problem.unsupported_reason and "ListNode" in problem.unsupported_reason
    result = SandboxExecutor(SandboxConfig(backend="host")).execute("", problem)
    assert result.status == "unsupported"
    assert result.error_message == problem.unsupported_reason
