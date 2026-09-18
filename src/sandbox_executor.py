"""
Sandbox Executor - Execute code in isolated sandbox environment.
"""

import json
import math
import numbers
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from src.models import (
    JudgeConfig,
    Problem,
    SandboxConfig,
    SandboxResult,
    TestCase,
    TestCaseResult,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

FUNCTION_RESULT_MARKER = "__LLM_HARNESS_FUNCTION_RESULT__"


class SandboxExecutionError(RuntimeError):
    """Structured failure raised by a sandbox backend."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


class SandboxExecutor:
    """Code sandbox executor for safe code execution."""

    def __init__(self, config: SandboxConfig):
        """
        Initialize sandbox executor.

        Args:
            config: Sandbox configuration
        """
        self.config = config
        logger.info("sandbox_initialized", config=config.model_dump())

    def execute(self, code: str, problem: Problem, stage: str = "public") -> SandboxResult:
        """
        Execute code against problem test cases.

        Args:
            code: Python function, class-method implementation, or stdin/stdout script
            problem: Problem with test cases

        Returns:
            SandboxResult with execution results

        Raises:
            ValueError: If code is invalid for the configured entry protocol
        """
        if problem.unsupported_reason:
            return SandboxResult(
                status="unsupported",
                all_passed=False,
                error_message=problem.unsupported_reason,
            )
        if problem.input_output_mode == "function" and self._entry_point_parts(
            problem.entry_point
        ) is None:
            return SandboxResult(
                status="unsupported",
                all_passed=False,
                error_message=f"Unsupported entry point: {problem.entry_point}",
            )

        test_cases = problem.test_cases_for(stage)
        logger.info(
            "executing_code", problem_id=problem.problem_id, stage=stage, num_tests=len(test_cases)
        )

        if not test_cases:
            message = f"No test cases configured for stage '{stage}'"
            return SandboxResult(status="sandbox_error", all_passed=False, error_message=message)

        if self.config.backend == "docker" and not self._docker_available():
            message = (
                "Docker sandbox backend unavailable; start Docker Desktop and ensure "
                f"image '{self.config.docker_image}' is available"
            )
            return SandboxResult(
                status="backend_unavailable",
                test_results=[
                    TestCaseResult(
                        test_case_index=index,
                        passed=False,
                        expected_output=test_case.expected_output,
                        error_message=message,
                        status="backend_unavailable",
                    )
                    for index, test_case in enumerate(test_cases)
                ],
                all_passed=False,
                error_message=message,
            )

        # Validate code contains solution function
        if not self._validate_code(code, problem):
            if problem.input_output_mode == "stdin_stdout":
                raise ValueError("Code must contain a stdin/stdout program")
            target = self._entry_point_parts(problem.entry_point)
            if not target or (target[0] == "solution" and target[1] is None):
                raise ValueError("Code must define a 'solution' function")
            raise ValueError("Code must define the configured entry point")

        # Check for disallowed imports
        self._check_imports(code)

        test_results = []
        start_time = time.time()

        for i, test_case in enumerate(test_cases):
            result = self._execute_single_test(code, test_case, i, problem)
            test_results.append(result)

        total_time = time.time() - start_time
        all_passed = all(r.passed for r in test_results)

        if all_passed:
            status = "success"
        else:
            resource_statuses = {
                "backend_unavailable",
                "timeout",
                "memory_error",
                "output_limit",
                "process_limit",
                "unsupported",
            }
            resource_failures = [
                result.status for result in test_results if result.status in resource_statuses
            ]
            status = resource_failures[0] if resource_failures else "failed"

        sandbox_result = SandboxResult(
            status=status,
            test_results=test_results,
            execution_time=total_time,
            all_passed=all_passed,
        )

        logger.info(
            "execution_completed",
            problem_id=problem.problem_id,
            status=status,
            passed=sum(1 for r in test_results if r.passed),
            total=len(test_results),
            time=total_time,
        )

        return sandbox_result

    def _docker_available(self) -> bool:
        """Return whether Docker CLI and its daemon are available."""
        if shutil.which("docker") is None:
            return False
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0 or not result.stdout.strip():
            return False
        try:
            image = subprocess.run(
                ["docker", "image", "inspect", self.config.docker_image],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return image.returncode == 0

    def health_check(self) -> tuple[bool, str | None]:
        """
        Probe sandbox availability through the real execution path.

        Runs a minimal known-good solution against a trivial problem via
        ``execute()``, so the probe inherits the exact backend, resource
        limits and cleanup semantics of a real evaluation run.

        Returns:
            (ok, detail) — detail is None on success, otherwise an
            actionable failure description
        """
        if self.config.backend == "docker" and not self._docker_available():
            return False, (
                "Docker sandbox backend unavailable; start Docker Desktop and ensure "
                f"image '{self.config.docker_image}' is available"
            )

        probe_problem = Problem(
            problem_id="__preflight__",
            title="Sandbox preflight",
            description="Minimal probe used by health_check; never shown to the model.",
            difficulty="easy",
            test_cases=[TestCase(input={"x": 1}, expected_output=1)],
        )
        probe_code = "def solution(x=None):\n    return x"

        try:
            result = self.execute(probe_code, probe_problem)
        except Exception as exc:
            return False, f"Sandbox probe execution failed: {exc}"

        failing_statuses = {"backend_unavailable", "sandbox_error"}
        if result.status in failing_statuses or any(
            tc.status in failing_statuses for tc in result.test_results
        ):
            detail = result.error_message or "; ".join(
                filter(None, (tc.error_message for tc in result.test_results))
            )
            return False, detail or "Sandbox probe execution failed"

        return True, None

    def _build_docker_command(
        self, workdir: str, runner_path: str, container_name: str | None = None
    ) -> list[str]:
        """Build a least-privilege Docker invocation."""
        return [
            "docker",
            "run",
            "--rm",
            "--interactive",
            *(["--name", container_name] if container_name else []),
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self.config.max_processes),
            "--memory",
            f"{self.config.memory_limit_mb}m",
            "--memory-swap",
            f"{self.config.memory_limit_mb}m",
            "--cpus",
            "1",
            "--user",
            "65532:65532",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--env",
            "PYTHONUNBUFFERED=1",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--mount",
            f"type=bind,src={workdir},dst=/workspace,readonly",
            "--workdir",
            "/workspace",
            self.config.docker_image,
            "python",
            f"/workspace/{Path(runner_path).name}",
        ]

    def _validate_code(self, code: str, problem: Problem | None = None) -> bool:
        """
        Validate code contains required solution function.

        Args:
            code: Python code

        Returns:
            True if valid
        """
        if not code or (problem and problem.input_output_mode == "stdin_stdout"):
            return bool(code and code.strip()) if problem else False

        entry_point = problem.entry_point if problem else "solution(**test_input)"
        target = self._entry_point_parts(entry_point)
        if target is None:
            return False
        class_name, method_name = target
        if method_name:
            return bool(
                re.search(rf"class\s+{re.escape(class_name)}\b", code)
                and re.search(rf"def\s+{re.escape(method_name)}\s*\(", code)
            )
        return bool(re.search(rf"def\s+{re.escape(class_name)}\s*\(", code))

    @staticmethod
    def _entry_point_parts(entry_point: str) -> tuple[str, str | None] | None:
        """Parse a function or simple class-method entry signature."""
        match = re.match(
            r"^\s*([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?\s*\([^()\n]*\)\s*$",
            entry_point or "",
        )
        if not match:
            return None
        return match.group(1), match.group(2)

    def _function_invocation(self, problem: Problem, namespace: str = "") -> str:
        """Build the safe callable expression for a function-style problem."""
        target = self._entry_point_parts(problem.entry_point)
        if target is None:
            raise SandboxExecutionError(
                "unsupported", f"Unsupported entry point: {problem.entry_point}"
            )
        class_name, method_name = target
        target_expr = f"{namespace}[{class_name!r}]" if namespace else class_name
        if method_name:
            return f"{target_expr}().{method_name}"
        return target_expr

    def _check_imports(self, code: str) -> None:
        """
        Check for disallowed imports.

        Args:
            code: Python code

        Raises:
            ValueError: If disallowed import found
        """
        # Extract all import statements
        import_pattern = r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        imports = re.findall(import_pattern, code, re.MULTILINE)

        allowed = set(self.config.allowed_imports)

        for imp in imports:
            if imp not in allowed:
                raise ValueError(f"Disallowed import: {imp}. Allowed: {allowed}")

    def _execute_single_test(
        self,
        code: str,
        test_case: TestCase,
        index: int,
        problem: Problem | None = None,
    ) -> TestCaseResult:
        """
        Execute code against single test case.

        Args:
            code: Python code
            test_case: Test case to run
            index: Test case index

        Returns:
            TestCaseResult
        """
        try:
            start_time = time.time()

            # Execute in subprocess for isolation
            if problem and problem.input_output_mode == "stdin_stdout":
                if self.config.backend == "docker":
                    raw_output = self._run_in_docker(code, test_case.input, problem)
                else:
                    raw_output = self._run_in_subprocess(code, test_case.input, problem)
                actual_output = self._parse_stdout_output(
                    raw_output, test_case.expected_output, problem.judge_config
                )
            elif self.config.backend == "docker":
                actual_output = self._run_in_docker(code, test_case.input, problem)
            else:
                actual_output = self._run_in_subprocess(code, test_case.input, problem)

            execution_time = time.time() - start_time

            # Check timeout
            if execution_time > self.config.timeout_seconds:
                return TestCaseResult(
                    test_case_index=index,
                    passed=False,
                    actual_output=None,
                    expected_output=test_case.expected_output,
                    error_message=f"Timeout exceeded ({execution_time:.2f}s > {self.config.timeout_seconds}s)",
                    execution_time=execution_time,
                    status="timeout",
                )

            # Compare output
            passed = self._compare_outputs(
                actual_output,
                test_case.expected_output,
                problem.judge_config if problem else None,
                text_output=bool(
                    problem
                    and problem.input_output_mode == "stdin_stdout"
                    and problem.judge_config.output_format != "json"
                ),
            )

            status = "passed" if passed else "wrong_answer"
            error_message = (
                None if passed else f"Expected {test_case.expected_output}, got {actual_output}"
            )

            return TestCaseResult(
                test_case_index=index,
                passed=passed,
                actual_output=actual_output,
                expected_output=test_case.expected_output,
                error_message=error_message,
                execution_time=execution_time,
                status=status,
            )

        except SandboxExecutionError as exc:
            return TestCaseResult(
                test_case_index=index,
                passed=False,
                actual_output=None,
                expected_output=test_case.expected_output,
                error_message=str(exc),
                execution_time=time.time() - start_time,
                status=exc.status,
            )

        except subprocess.TimeoutExpired:
            return TestCaseResult(
                test_case_index=index,
                passed=False,
                actual_output=None,
                expected_output=test_case.expected_output,
                error_message=f"Timeout: exceeded {self.config.timeout_seconds}s",
                execution_time=self.config.timeout_seconds,
                status="timeout",
            )

        except Exception as e:
            return TestCaseResult(
                test_case_index=index,
                passed=False,
                actual_output=None,
                expected_output=test_case.expected_output,
                error_message=f"Runtime error: {str(e)}",
                execution_time=time.time() - start_time,
                status="runtime_error",
            )

    def _run_in_subprocess(
        self,
        code: str,
        test_input: Any,
        problem: Problem | None = None,
    ) -> Any:
        """
        Run code in subprocess for isolation.

        Args:
            code: Python code
            test_input: Function arguments or stdin payload

        Returns:
            Function output

        Raises:
            subprocess.TimeoutExpired: If timeout exceeded
            Exception: If execution fails
        """
        if problem and problem.input_output_mode == "stdin_stdout":
            wrapper = code
            input_data = self._serialize_stdin_input(test_input)
            result_marker = None
        else:
            invocation = (
                self._function_invocation(problem, "_user_globals")
                if problem
                else "_user_globals['solution']"
            )
            result_marker = f"{FUNCTION_RESULT_MARKER}:{uuid.uuid4().hex}:"
            wrapper = f"""
import json as _harness_json
import os as _harness_os
import sys as _harness_sys
_harness_dumps = _harness_json.dumps
_harness_loads = _harness_json.loads
_harness_write = _harness_os.write
_harness_fd = _harness_os.dup(2)
_user_globals = {{"__name__": "__candidate__"}}
exec({code!r}, _user_globals, _user_globals)

if __name__ == "__main__":
    test_input = _harness_loads(_harness_sys.argv[1])
    target = {invocation}
    if isinstance(test_input, dict):
        result = target(**test_input)
    elif isinstance(test_input, (list, tuple)):
        result = target(*test_input)
    else:
        result = target(test_input)
    _harness_write(_harness_fd, ({result_marker!r} + _harness_dumps(result) + "\\n").encode())
"""
            input_data = None

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(wrapper)
            temp_file = f.name

        try:
            # Run subprocess
            import json

            command = (
                [sys.executable, temp_file]
                if problem and problem.input_output_mode == "stdin_stdout"
                else [sys.executable, temp_file, json.dumps(test_input)]
            )
            result = self._run_command(
                command,
                timeout=self.config.timeout_seconds + 1,
                cwd=str(Path(temp_file).parent),
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONNOUSERSITE": "1",
                    "HOME": str(Path(temp_file).parent),
                },
                input_data=input_data,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Execution failed: {result.stderr}")

            if problem and problem.input_output_mode == "stdin_stdout":
                return result.stdout
            return self._parse_function_result(result.stderr, result.stdout, result_marker)

        finally:
            # Cleanup
            Path(temp_file).unlink(missing_ok=True)

    def _run_command(
        self,
        command: list[str],
        timeout: float,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        cleanup=None,
        input_data: bytes | None = None,
    ):
        """Run a command while bounding combined stdout/stderr in the parent."""
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if input_data is not None else None,
            env=env,
            cwd=cwd,
            start_new_session=(os.name != "nt"),
        )
        selector = selectors.DefaultSelector()
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        input_offset = 0
        if input_data is not None and process.stdin is not None:
            try:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            except OSError:
                process.stdin.close()

        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        deadline = time.monotonic() + timeout

        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SandboxExecutionError("timeout", "Sandbox timeout exceeded")
                for key, mask in selector.select(remaining):
                    if key.data == "stdin":
                        try:
                            written = os.write(
                                key.fileobj.fileno(), input_data[input_offset:]
                            )
                            input_offset += written
                            if input_offset >= len(input_data):
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                        except (BrokenPipeError, OSError):
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                        continue
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffers[key.data].extend(chunk)
                    if (
                        sum(len(buffer) for buffer in buffers.values())
                        > self.config.max_output_bytes
                    ):
                        raise SandboxExecutionError(
                            "output_limit", "Sandbox output exceeded the configured limit"
                        )
            returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            return subprocess.CompletedProcess(
                command,
                returncode,
                stdout=bytes(buffers["stdout"]).decode(errors="replace"),
                stderr=bytes(buffers["stderr"]).decode(errors="replace"),
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxExecutionError("timeout", "Sandbox timeout exceeded") from exc
        finally:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            selector.close()
            if os.name != "nt" or process.poll() is None:
                self._terminate_process_group(process)
            if process.poll() is None:
                process.wait()
            if cleanup is not None:
                try:
                    cleanup()
                except Exception as exc:
                    logger.warning("sandbox_cleanup_failed", error=str(exc))

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen) -> None:
        """Terminate the command and any children created in its process group."""
        if os.name == "nt":
            process.kill()
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _run_in_docker(
        self,
        code: str,
        test_input: Any,
        problem: Problem | None = None,
    ) -> Any:
        """Run one test in a network-disabled, resource-limited container."""
        if problem and problem.input_output_mode == "stdin_stdout":
            wrapper = code
            input_data = self._serialize_stdin_input(test_input)
        else:
            invocation = (
                self._function_invocation(problem, "_user_globals")
                if problem
                else "_user_globals['solution']"
            )
            result_marker = f"{FUNCTION_RESULT_MARKER}:{uuid.uuid4().hex}:"
            wrapper = f"""
import json as _harness_json
import os as _harness_os
_harness_dumps = _harness_json.dumps
_harness_loads = _harness_json.loads
_harness_write = _harness_os.write
_harness_fd = _harness_os.dup(2)
_user_globals = {{"__name__": "__candidate__"}}
exec({code!r}, _user_globals, _user_globals)
test_input = _harness_loads({json.dumps(json.dumps(test_input))})
target = {invocation}
if isinstance(test_input, dict):
    result = target(**test_input)
elif isinstance(test_input, (list, tuple)):
    result = target(*test_input)
else:
    result = target(test_input)
_harness_write(_harness_fd, ({result_marker!r} + _harness_dumps(result) + "\\n").encode())
"""
            input_data = None
        with tempfile.TemporaryDirectory(prefix="llm-harness-sandbox-") as workdir:
            os.chmod(workdir, 0o755)
            runner_path = Path(workdir) / "runner.py"
            runner_path.write_text(wrapper, encoding="utf-8")
            runner_path.chmod(0o644)
            container_name = f"llm-harness-{uuid.uuid4().hex}"
            command = self._build_docker_command(workdir, str(runner_path), container_name)

            def cleanup_container():
                subprocess.run(
                    ["docker", "rm", "--force", container_name],
                    capture_output=True,
                    timeout=5,
                )

            result = self._run_command(
                command,
                timeout=self.config.timeout_seconds + 2,
                env={"PATH": os.environ.get("PATH", "")},
                cleanup=cleanup_container,
                input_data=input_data,
            )
            if result.returncode != 0:
                stderr = result.stderr.lower()
                status = (
                    "memory_error"
                    if result.returncode == 137 or "out of memory" in stderr or "oom" in stderr
                    else "sandbox_error"
                )
                if (
                    "pids" in stderr
                    or ("process" in stderr and "limit" in stderr)
                    or "resource temporarily unavailable" in stderr
                    or "blockingioerror" in stderr
                    or "errno 11" in stderr
                ):
                    status = "process_limit"
                if result.returncode in {125, 126, 127} and (
                    "unable to find image" in stderr
                    or "executable file not found" in stderr
                    or "no such file or directory" in stderr
                ):
                    status = "backend_unavailable"
                raise SandboxExecutionError(
                    status,
                    f"Docker execution failed: {result.stderr[-400:]}",
                )
            if problem and problem.input_output_mode == "stdin_stdout":
                return result.stdout
            return self._parse_function_result(result.stderr, result.stdout, result_marker)

    @staticmethod
    def _serialize_stdin_input(test_input: Any) -> bytes:
        """Serialize a test input into the bytes supplied to stdin."""
        if isinstance(test_input, bytes):
            return test_input
        if isinstance(test_input, str):
            return test_input.encode("utf-8")
        return (json.dumps(test_input) + "\n").encode("utf-8")

    @staticmethod
    def _parse_function_result(
        stderr: str, stdout: str = "", result_marker: str | None = None
    ) -> Any:
        """Read the function result from its dedicated stderr marker."""
        marker = result_marker or FUNCTION_RESULT_MARKER
        for line in reversed(stderr.splitlines()):
            if line.startswith(marker):
                payload = line[len(marker) :]
                try:
                    return json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise SandboxExecutionError(
                        "runtime_error", "Function result channel contained invalid JSON"
                    ) from exc
        # Keep compatibility with mocked/legacy runners that returned only a
        # JSON stdout payload. New wrappers always use the dedicated marker.
        if stdout.strip():
            try:
                return json.loads(stdout.strip())
            except json.JSONDecodeError:
                pass
        raise SandboxExecutionError(
            "runtime_error", "Function result channel marker was not produced"
        )

    @staticmethod
    def _parse_stdout_output(
        raw_output: str, expected_output: Any, judge_config: JudgeConfig
    ) -> Any:
        """Parse stdout according to an explicit text or JSON output format."""
        if judge_config.output_format == "text" or (
            judge_config.output_format == "auto" and isinstance(expected_output, str)
        ):
            return raw_output
        try:
            return json.loads(raw_output.strip())
        except json.JSONDecodeError as exc:
            raise SandboxExecutionError(
                "runtime_error", "Standard output is not valid JSON"
            ) from exc

    def _compare_outputs(
        self,
        actual: Any,
        expected: Any,
        judge_config: JudgeConfig | None = None,
        text_output: bool = False,
    ) -> bool:
        """
        Compare actual and expected outputs.

        Args:
            actual: Actual output
            expected: Expected output

        Returns:
            True if outputs match
        """
        config = judge_config or JudgeConfig()
        if text_output and isinstance(actual, str) and isinstance(expected, str):
            if config.whitespace == "trim":
                return actual.strip() == expected.strip()
            if config.whitespace == "tokens":
                return actual.split() == expected.split()
            return actual == expected

        if config.comparison == "exact":
            return actual == expected
        if config.comparison == "unordered":
            return self._compare_unordered(actual, expected, config.float_tolerance)
        return self._compare_float_tolerant(actual, expected, config.float_tolerance)

    @classmethod
    def _compare_float_tolerant(cls, actual: Any, expected: Any, tolerance: float) -> bool:
        """Recursively compare nested values with a configured float tolerance."""
        if isinstance(actual, numbers.Real) and not isinstance(actual, bool):
            if isinstance(expected, numbers.Real) and not isinstance(expected, bool):
                return math.isclose(
                    float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance
                )
            return False
        if isinstance(actual, dict) and isinstance(expected, dict):
            return set(actual) == set(expected) and all(
                cls._compare_float_tolerant(actual[key], expected[key], tolerance)
                for key in actual
            )
        if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
            return len(actual) == len(expected) and all(
                cls._compare_float_tolerant(a, e, tolerance)
                for a, e in zip(actual, expected, strict=True)
            )
        return actual == expected

    @classmethod
    def _compare_unordered(cls, actual: Any, expected: Any, tolerance: float) -> bool:
        """Compare list-like results as multisets without sorting arbitrary values."""
        if not isinstance(actual, (list, tuple)) or not isinstance(expected, (list, tuple)):
            return cls._compare_float_tolerant(actual, expected, tolerance)
        if len(actual) != len(expected):
            return False
        adjacency = [
            [
                expected_index
                for expected_index, expected_item in enumerate(expected)
                if cls._compare_float_tolerant(actual_item, expected_item, tolerance)
            ]
            for actual_item in actual
        ]
        matched_actual = [-1] * len(expected)

        def find_match(actual_index: int, visited: set[int]) -> bool:
            for expected_index in adjacency[actual_index]:
                if expected_index in visited:
                    continue
                visited.add(expected_index)
                previous = matched_actual[expected_index]
                if previous == -1 or find_match(previous, visited):
                    matched_actual[expected_index] = actual_index
                    return True
            return False

        return all(find_match(index, set()) for index in range(len(actual)))
