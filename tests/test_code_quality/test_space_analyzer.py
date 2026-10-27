"""
Tests for Space Complexity Analyzer
"""

import pytest

from src.code_quality.space_analyzer import SpaceAnalyzer


class TestSpaceAnalyzer:
    """Test suite for SpaceAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return SpaceAnalyzer()

    def test_analyze_simple_code(self, analyzer):
        """Test analysis of simple code with minimal memory usage."""
        code = """
def solution(x):
    return x * 2
"""
        result = analyzer.analyze(code)
        # Profiling without a sandbox remains explicitly unavailable
        assert result.peak_memory_bytes is None
        assert result.peak_memory_mb is None
        assert result.memory_efficiency_score is None
        assert "Memory profiling requires sandbox executor" in result.analysis_notes

    def test_analyze_memory_intensive_code(self, analyzer):
        """Test analysis of code with higher memory usage."""
        code = """
def solution(n):
    # Create large list
    data = [i for i in range(n)]
    return len(data)

solution(10000)
"""
        result = analyzer.analyze(code)
        # Profiling without a sandbox remains explicitly unavailable
        assert result.peak_memory_bytes is None
        assert result.peak_memory_mb is None
        assert "Memory profiling requires sandbox executor" in result.analysis_notes

    def test_analyze_with_data_structures(self, analyzer):
        """Test analysis of code using various data structures."""
        code = """
def solution():
    # Create various data structures
    list_data = [i for i in range(100)]
    dict_data = {i: i*2 for i in range(100)}
    set_data = {i for i in range(100)}
    return len(list_data) + len(dict_data) + len(set_data)

solution()
"""
        result = analyzer.analyze(code)
        # Profiling without a sandbox remains explicitly unavailable
        assert result.peak_memory_bytes is None
        assert result.peak_memory_mb is None
        assert result.memory_efficiency_score is None
        assert "Memory profiling requires sandbox executor" in result.analysis_notes

    def test_efficiency_score_calculation(self, analyzer):
        """Test that efficiency score is calculated reasonably."""
        code = """
def solution():
    return 42
"""
        result = analyzer.analyze(code)
        # Profiling without a sandbox remains explicitly unavailable
        assert result.memory_efficiency_score is None
        assert "Memory profiling requires sandbox executor" in result.analysis_notes

    def test_analysis_notes_generation(self, analyzer):
        """Test that analysis notes are generated."""
        code = """
def solution():
    return 1
"""
        result = analyzer.analyze(code)
        # Should have notes list (even if empty)
        assert isinstance(result.analysis_notes, list)

    def test_invalid_code_handling(self, analyzer):
        """Test handling of invalid code."""
        invalid_code = "def broken syntax"
        result = analyzer.analyze(invalid_code)
        # Should return empty score without crashing
        assert result.peak_memory_bytes is None
        assert result.peak_memory_mb is None

    def test_empty_code_handling(self, analyzer):
        """Test handling of empty code."""
        result = analyzer.analyze("")
        # Should handle gracefully
        assert result is not None


def memory_problem(**updates):
    from src.models import Problem

    values = dict(
        problem_id="memory",
        title="Memory",
        description="Memory profiling regression",
        difficulty="easy",
        public_test_cases=[{"input": {"n": 8 * 1024 * 1024}, "expected_output": 1}],
    )
    values.update(updates)
    return Problem(**values)


def host_executor(**updates):
    from src.models import SandboxConfig
    from src.sandbox_executor import SandboxExecutor

    return SandboxExecutor(SandboxConfig(backend="host", **updates))


def test_real_child_peak_includes_temporary_allocations():
    executor = host_executor()
    problem = memory_problem()
    small = executor.execute_with_memory_profiling("def solution(n): return 1", problem)
    large = executor.execute_with_memory_profiling(
        "def solution(n):\n    data = bytearray(n)\n    del data\n    return 1", problem
    )
    assert set(large) == {1}
    assert large[1]["peak_bytes"] >= 8 * 1024 * 1024
    assert large[1]["peak_bytes"] > small[1]["peak_bytes"] + 7 * 1024 * 1024
    assert large[1]["current_bytes"] < large[1]["peak_bytes"]


def test_orchestrator_reports_real_space_score():
    from src.code_quality.analyzer import CodeQualityAnalyzer

    analyzer = CodeQualityAnalyzer(enable_time=False, enable_readability=False, enable_style=False)
    problem = memory_problem()
    executor = host_executor()
    small = analyzer.analyze("def solution(n): return 1", problem, executor).space_complexity
    large = analyzer.analyze(
        "def solution(n):\n    data = bytearray(n)\n    return 1", problem, executor
    ).space_complexity
    assert large.peak_memory_bytes >= 8 * 1024 * 1024
    assert large.peak_memory_mb >= 8
    assert 0 <= large.memory_efficiency_score < small.memory_efficiency_score <= 100


@pytest.mark.parametrize(
    "mode,entry,code,inp,out",
    [
        (
            "function",
            "Solution.solve(n)",
            "class Solution:\n    def solve(self,n):\n        data=bytearray(n)\n        return 1",
            {"n": 1048576},
            1,
        ),
        (
            "stdin_stdout",
            "main()",
            "n=int(input())\ndata=bytearray(n)\nprint(1)",
            "1048576\n",
            "1\n",
        ),
        (
            "stdin_stdout",
            "main()",
            "n=int(input())\ndata=bytearray(n)\nprint(1)\nraise SystemExit(0)",
            "1048576\n",
            "1\n",
        ),
    ],
)
def test_profile_preserves_protocol(mode, entry, code, inp, out):
    problem = memory_problem(
        input_output_mode=mode,
        entry_point=entry,
        public_test_cases=[{"input": inp, "expected_output": out}],
    )
    samples = host_executor().execute_with_memory_profiling(code, problem)
    assert samples[1]["peak_bytes"] >= 1048576


@pytest.mark.parametrize(
    "code",
    [
        "def solution(n): return 2",
        "def solution(n): raise ValueError('bad')",
        "def solution(n):\n    while True: pass",
    ],
)
def test_failed_runs_have_no_sample(code):
    assert (
        host_executor(timeout_seconds=1).execute_with_memory_profiling(code, memory_problem()) == {}
    )


def test_profile_uses_public_tests_only_and_keeps_host_tracing():
    import tracemalloc

    problem = memory_problem(hidden_test_cases=[{"input": {"n": "hidden"}, "expected_output": 1}])
    tracemalloc.start()
    try:
        samples = host_executor().execute_with_memory_profiling(
            "def solution(n):\n    data=bytearray(n)\n    return 1", problem
        )
        assert tracemalloc.is_tracing()
        assert samples[1]["peak_bytes"] >= 8 * 1024 * 1024
    finally:
        tracemalloc.stop()


def test_explicit_scaling_does_not_judge_against_original_output():
    problem = memory_problem(
        public_test_cases=[{"input": {"n": 1048576}, "expected_output": 1048576}]
    )
    samples = host_executor().execute_with_memory_profiling(
        "def solution(n):\n    data=bytearray(n)\n    return len(data)", problem, scales=[1, 2]
    )
    assert samples[2]["peak_bytes"] > samples[1]["peak_bytes"] + 1000000


def test_memory_score_formula_and_missing_samples():
    from unittest.mock import Mock

    from src.models import SandboxConfig

    sandbox = Mock(config=SandboxConfig(backend="host", memory_limit_mb=64))
    sandbox.execute_with_memory_profiling.return_value = {1: {"peak_bytes": 16 * 1048576}}
    result = SpaceAnalyzer().analyze(
        "def solution(n): return 1", sandbox_executor=sandbox, problem=memory_problem()
    )
    assert result.peak_memory_mb == 16
    assert result.memory_efficiency_score == 75
    sandbox.execute_with_memory_profiling.return_value = {}
    assert (
        SpaceAnalyzer()
        .analyze("", sandbox_executor=sandbox, problem=memory_problem())
        .memory_efficiency_score
        is None
    )
    sandbox.execute_with_memory_profiling.side_effect = RuntimeError("failure")
    result = SpaceAnalyzer().analyze("", sandbox_executor=sandbox, problem=memory_problem())
    assert result.memory_efficiency_score is None
    assert result.analysis_notes


def test_multiple_public_cases_use_maximum_peak():
    problem = memory_problem(
        public_test_cases=[
            {"input": {"n": 1048576}, "expected_output": 1},
            {"input": {"n": 4 * 1048576}, "expected_output": 1},
        ]
    )
    result = host_executor().execute_with_memory_profiling(
        "def solution(n):\n    data=bytearray(n)\n    return 1", problem
    )
    assert result[1]["peak_bytes"] >= 4 * 1048576


@pytest.mark.parametrize("stdin_mode", [False, True])
def test_docker_runner_memory_protocol(monkeypatch, stdin_mode):
    """Run the generated Docker script locally; check output and cleanup boundaries."""
    import subprocess
    import sys
    from pathlib import Path

    from src.models import SandboxConfig
    from src.sandbox_executor import SandboxExecutor

    executor = SandboxExecutor(SandboxConfig(backend="docker"))
    monkeypatch.setattr(executor, "_docker_available", lambda: True)
    cleaned = []
    run = subprocess.run

    def local_runner(command, **kwargs):
        mount = command[command.index("--mount") + 1]
        workdir = mount.split("src=", 1)[1].split(",dst=", 1)[0]
        runner = Path(workdir) / "runner.py"
        return run(
            [sys.executable, str(runner)],
            capture_output=True,
            text=True,
            timeout=5,
            input=kwargs["input_data"].decode() if kwargs["input_data"] is not None else None,
        )

    monkeypatch.setattr(executor, "_run_command", local_runner)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: cleaned.append(cmd))
    problem = memory_problem()
    code = "def solution(n):\n    data=bytearray(n)\n    return 1"
    if stdin_mode:
        problem = memory_problem(
            input_output_mode="stdin_stdout",
            entry_point="main()",
            public_test_cases=[{"input": "8388608\n", "expected_output": "1\n"}],
        )
        code = "n=int(input())\ndata=bytearray(n)\nprint(1)"
    samples = executor.execute_with_memory_profiling(code, problem)
    assert samples[1]["peak_bytes"] >= 8 * 1048576
    assert len(cleaned) == 1 and cleaned[0][:3] == ["docker", "rm", "--force"]


def test_candidate_disabling_tracing_does_not_report_zero_memory():
    executor = host_executor(allowed_imports=["tracemalloc"])
    samples = executor.execute_with_memory_profiling(
        "import tracemalloc\ndef solution(n):\n    tracemalloc.stop()\n    data=bytearray(n)\n    return 1",
        memory_problem(),
    )
    assert samples == {}


def test_missing_sample_cannot_fall_back_to_candidate_stdout(monkeypatch):
    import subprocess

    executor = host_executor()
    monkeypatch.setattr(
        executor,
        "_run_command",
        lambda *args, **kw: subprocess.CompletedProcess(
            args[0], 0, stdout='{"current_bytes":0,"peak_bytes":0}', stderr=""
        ),
    )
    problem = memory_problem(
        input_output_mode="stdin_stdout",
        entry_point="main()",
        public_test_cases=[{"input": "", "expected_output": '{"current_bytes":0,"peak_bytes":0}'}],
    )
    assert executor.execute_with_memory_profiling("print('unused')", problem) == {}


def test_profile_preserves_stdin_script_file_context():
    problem = memory_problem(
        input_output_mode="stdin_stdout",
        entry_point="main()",
        public_test_cases=[{"input": "", "expected_output": "1\n"}],
    )
    assert host_executor().execute_with_memory_profiling(
        "print(int(__file__.endswith('.py')))", problem
    )
