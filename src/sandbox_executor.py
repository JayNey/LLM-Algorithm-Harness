"""
Sandbox Executor - Execute code in isolated sandbox environment.
"""

import json
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
    Problem,
    SandboxConfig,
    SandboxResult,
    TestCase,
    TestCaseResult,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


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
            code: Python code to execute (must define a 'solution' function)
            problem: Problem with test cases

        Returns:
            SandboxResult with execution results

        Raises:
            ValueError: If code is invalid or missing solution function
        """
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
        if not self._validate_code(code):
            raise ValueError("Code must define a 'solution' function")

        # Check for disallowed imports
        self._check_imports(code)

        test_results = []
        start_time = time.time()

        for i, test_case in enumerate(test_cases):
            result = self._execute_single_test(code, test_case, i)
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

    def _build_docker_command(
        self, workdir: str, runner_path: str, container_name: str | None = None
    ) -> list[str]:
        """Build a least-privilege Docker invocation."""
        return [
            "docker",
            "run",
            "--rm",
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

    def _validate_code(self, code: str) -> bool:
        """
        Validate code contains required solution function.

        Args:
            code: Python code

        Returns:
            True if valid
        """
        # Check for 'def solution' pattern
        pattern = r"def\s+solution\s*\("
        return bool(re.search(pattern, code))

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

    def _execute_single_test(self, code: str, test_case: TestCase, index: int) -> TestCaseResult:
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
            if self.config.backend == "docker":
                actual_output = self._run_in_docker(code, test_case.input)
            else:
                actual_output = self._run_in_subprocess(code, test_case.input)

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
            passed = self._compare_outputs(actual_output, test_case.expected_output)

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

    def _run_in_subprocess(self, code: str, test_input: dict[str, Any]) -> Any:
        """
        Run code in subprocess for isolation.

        Args:
            code: Python code
            test_input: Test input dictionary

        Returns:
            Function output

        Raises:
            subprocess.TimeoutExpired: If timeout exceeded
            Exception: If execution fails
        """
        # Create wrapper script
        wrapper = f"""
import sys
import json

# User code
{code}

# Execute test
if __name__ == "__main__":
    test_input = json.loads(sys.argv[1])
    result = solution(**test_input)
    print(json.dumps(result))
"""

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(wrapper)
            temp_file = f.name

        try:
            # Run subprocess
            import json

            result = self._run_command(
                [sys.executable, temp_file, json.dumps(test_input)],
                timeout=self.config.timeout_seconds + 1,
                cwd=str(Path(temp_file).parent),
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONNOUSERSITE": "1",
                    "HOME": str(Path(temp_file).parent),
                },
            )

            if result.returncode != 0:
                raise RuntimeError(f"Execution failed: {result.stderr}")

            # Parse output
            import json

            return json.loads(result.stdout.strip())

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
    ):
        """Run a command while bounding combined stdout/stderr in the parent."""
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            start_new_session=(os.name != "nt"),
        )
        selector = selectors.DefaultSelector()
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        deadline = time.monotonic() + timeout

        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SandboxExecutionError("timeout", "Sandbox timeout exceeded")
                for key, _ in selector.select(remaining):
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

    def _run_in_docker(self, code: str, test_input: dict[str, Any]) -> Any:
        """Run one test in a network-disabled, resource-limited container."""
        wrapper = f"""
import json
{code}
test_input = json.loads({json.dumps(json.dumps(test_input))})
result = solution(**test_input)
print(json.dumps(result))
"""
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
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError as exc:
                raise SandboxExecutionError(
                    "sandbox_error", "Sandbox returned invalid JSON"
                ) from exc

    def _compare_outputs(self, actual: Any, expected: Any) -> bool:
        """
        Compare actual and expected outputs.

        Args:
            actual: Actual output
            expected: Expected output

        Returns:
            True if outputs match
        """
        # Handle floating point comparison
        if isinstance(actual, float) and isinstance(expected, float):
            return abs(actual - expected) < 1e-6

        # Handle lists of floats
        if isinstance(actual, list) and isinstance(expected, list):
            if len(actual) != len(expected):
                return False
            return all(
                abs(a - e) < 1e-6 if isinstance(a, float) and isinstance(e, float) else a == e
                for a, e in zip(actual, expected, strict=True)
            )

        # Standard equality
        return actual == expected
