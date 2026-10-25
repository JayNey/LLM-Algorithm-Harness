"""Fast correctness checks for performance tooling; no machine-specific time gates."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "harness_perf", Path(__file__).with_name("benchmark.py")
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_percentiles_and_failures_are_not_hidden():
    result = benchmark.summary(list(range(1, 101)), 2, {"TimeoutError": 2})
    assert (result["p50_ms"], result["p95_ms"], result["p99_ms"]) == (50, 95, 99)
    assert result["throughput_per_s"] == 50
    assert result["errors"] == 2
    assert result["error_types"] == {"TimeoutError": 2}


def test_measured_failures_and_warmup():
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls > 3:
            raise TimeoutError("must not expose sensitive exception text")

    result = benchmark.measure(operation, 4, 1)
    assert calls == 7
    assert result["requests"] == result["errors"] == 4
    assert result["error_types"] == {"TimeoutError": 4}
    assert "sensitive" not in str(result)


def test_invalid_setup_is_fatal():
    with pytest.raises(TimeoutError):
        benchmark.measure(lambda: (_ for _ in ()).throw(TimeoutError()), 1)


def test_gate_rejects_errors_and_latency():
    report = {"http": {"health": {"errors": 0, "p95_ms": 10}}, "database": {}}
    assert not benchmark.failed(report)
    assert not benchmark.failed(report, 10)
    assert benchmark.failed(report, 9)
    report["http"]["health"]["errors"] = 1
    assert benchmark.failed(report)


@pytest.mark.performance
def test_real_concurrent_api_and_database_benchmark():
    report = benchmark.run_benchmark(rows=25, samples=4, concurrency=4)
    assert report["configuration"]["rows_per_table"] == 25
    assert len(report["http"]) == 3
    assert len(report["database"]) == 4
    assert not benchmark.failed(report)
    for group in ("http", "database"):
        for result in report[group].values():
            assert result["requests"] == 4
            assert result["p50_ms"] <= result["p95_ms"] <= result["p99_ms"]
            assert result["throughput_per_s"] > 0
    assert "token" not in str(report).lower()


@pytest.mark.parametrize(
    "option,value",
    [("--rows", "0"), ("--samples", "-1"), ("--concurrency", "0"), ("--max-p95-ms", "nan")],
)
def test_cli_rejects_invalid_arguments(option, value):
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("benchmark.py")), option, value],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 2


@pytest.mark.parametrize(
    "profile,expected",
    [("load", [10, None]), ("concurrency", [10, None]), ("stress", [10, 20, 40, 80, None])],
)
def test_load_shapes_in_separate_process(profile, expected):
    if importlib.util.find_spec("locust") is None:
        pytest.skip("install .[performance] to check Locust shapes")
    import os

    script = """
import importlib.util
s = importlib.util.spec_from_file_location("load", "tests/performance/locustfile.py")
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
shape = m.ApiShape()
actual = []
for t in TIMES:
    shape.get_run_time = lambda: t
    result = shape.tick()
    actual.append(result[0] if result else None)
    if result:
        assert result[1] == (result[0] if m.PROFILE == "concurrency" else max(1, result[0] / 5))
assert actual == EXPECTED, actual
from types import SimpleNamespace
for count, failures, latency, exit_code in [(0, 0, 0, 1), (2, 1, 1, 1), (2, 0, 1001, 1), (2, 0, 1000, None)]:
    stats = SimpleNamespace(num_requests=count, num_failures=failures, get_response_time_percentile=lambda _: latency)
    environment = SimpleNamespace(stats=SimpleNamespace(total=stats), process_exit_code=None)
    m.check_results(environment)
    assert environment.process_exit_code == exit_code
""".replace("TIMES", repr([60 * i for i in range(len(expected))])).replace(
        "EXPECTED", repr(expected)
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "PERF_PROFILE": profile,
            "PERF_USERS": "10",
            "PERF_STAGE_SECONDS": "60",
            "PERF_MAX_P95_MS": "1000",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
