"""
Offline end-to-end regression tests with a fixed-response model double (issue #20).

No network access happens in this module: the model is a fixed-response
double injected at the harness boundary, and the sandbox runs the `host`
backend locally. Success and failure chains assert the on-disk result files
directly, and negative inputs must fail loudly instead of being mistaken
for successes.
"""

import glob
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import LLMResponse, TokenUsage

CORRECT_SOLUTION = "def solution(x):\n    return x + 1"
WRONG_SOLUTION = "def solution(x):\n    return x + 100"


def _write_dataset(tmp_path):
    dataset = tmp_path / "problems.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "problem_id": "e2e-1",
                    "title": "Add One",
                    "description": "Return x plus one for the offline e2e regression run.",
                    "difficulty": "easy",
                    "tags": [],
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                }
            ]
        ),
        encoding="utf-8",
    )
    return dataset


def _write_config(tmp_path, dataset, strategies=None):
    config = tmp_path / "config.json"
    payload = {
        "dataset_path": str(dataset),
        "output_dir": str(tmp_path / "results"),
        "llm_config": {
            "provider": "openai",
            "api_key": "offline-test-key",
            "model": "fixed-double",
            "timeout": 30,
        },
        "sandbox_config": {"backend": "host"},
        "strategies": strategies
        if strategies is not None
        else [{"name": "vanilla", "max_iterations": 1}],
    }
    config.write_text(json.dumps(payload), encoding="utf-8")
    return config


def _llm_factory(solution_text):
    """Fixed-response model double factory bound to the harness injection point."""

    def factory(config):
        double = MagicMock()
        double.generate.return_value = LLMResponse(
            text=f"```python\n{solution_text}\n```",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="fixed-double",
            finish_reason="stop",
        )
        return double

    return factory


def _run_main(argv):
    from src.main import main

    exit_code = 0
    with patch("sys.argv", ["main.py"] + argv):
        try:
            main()
        except SystemExit as exc:
            exit_code = exc.code or 0
    return exit_code


def _latest_run_dir(tmp_path):
    runs = sorted(glob.glob(str(tmp_path / "results" / "run-*")))
    assert runs, "run directory must exist after a successful evaluation"
    return runs[-1]


# ============================================================================
# Empty strategies must fail loudly (task 1.1)
# ============================================================================


def test_run_without_strategies_raises(tmp_path):
    """An empty strategy list is an explicit error, not a silent empty run."""
    from src.harness import AlgorithmHarness
    from src.models import HarnessConfig, LLMConfig, SandboxConfig

    dataset = _write_dataset(tmp_path)
    config = HarnessConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        llm_config=LLMConfig(
            provider="openai", api_key="offline-test-key", model="fixed-double"
        ),
        sandbox_config=SandboxConfig(backend="host"),
        strategies=[],
    )
    harness = AlgorithmHarness(config)

    with pytest.raises(ValueError, match="No strategies configured"):
        harness.run()


# ============================================================================
# End-to-end success / failure chains (task 1.2)
# ============================================================================


def test_e2e_success_chain_records_exact_results(tmp_path):
    """Correct answer chain: CLI -> dataset -> strategy -> sandbox -> result files."""
    dataset = _write_dataset(tmp_path)
    config_path = _write_config(tmp_path, dataset)

    with patch("src.harness.LLMClient", side_effect=_llm_factory(CORRECT_SOLUTION)):
        exit_code = _run_main(["--config", str(config_path)])

    assert exit_code == 0
    run_dir = _latest_run_dir(tmp_path)

    summary = json.loads((Path(run_dir) / "summary.json").read_text())
    vanilla_summary = summary["strategies"]["vanilla"]
    assert vanilla_summary["total_problems"] == 1
    assert vanilla_summary["solved_problems"] == 1
    assert vanilla_summary["success_rate"] == 1.0
    assert vanilla_summary["total_tokens"] == 15

    results = json.loads((Path(run_dir) / "vanilla_results.json").read_text())
    assert len(results) == 1
    record = results[0]
    assert record["status"] == "success"
    assert record["failure_category"] is None
    assert record["total_tokens"] == 15
    assert record["execution_time_seconds"] > 0
    assert len(record["llm_traces"]) == 1


def test_e2e_failure_chain_records_wrong_answer_precisely(tmp_path):
    """Wrong answer chain: failure category and per-case outputs are exact."""
    dataset = _write_dataset(tmp_path)
    config_path = _write_config(tmp_path, dataset)

    with patch("src.harness.LLMClient", side_effect=_llm_factory(WRONG_SOLUTION)):
        exit_code = _run_main(["--config", str(config_path)])

    assert exit_code == 0
    run_dir = _latest_run_dir(tmp_path)

    results = json.loads((Path(run_dir) / "vanilla_results.json").read_text())
    record = results[0]
    assert record["status"] == "failed"
    assert record["failure_category"] == "wrong_answer"
    assert record["test_results"][0]["actual_output"] == 101
    assert record["test_results"][0]["expected_output"] == 2

    summary = json.loads((Path(run_dir) / "summary.json").read_text())
    assert summary["strategies"]["vanilla"]["solved_problems"] == 0


# ============================================================================
# Negative inputs must fail loudly (task 1.3)
# ============================================================================


def test_missing_dataset_fails_without_output_dir(tmp_path):
    """A missing dataset exits non-zero and creates no results directory."""
    config_path = _write_config(tmp_path, tmp_path / "missing-problems.json")

    exit_code = _run_main(["--config", str(config_path)])

    assert exit_code == 1
    assert not (tmp_path / "results").exists()


def test_bad_config_fails_without_output_dir(tmp_path):
    """A malformed config file exits non-zero with a config error."""
    bad_config = tmp_path / "bad.json"
    bad_config.write_text("{ this is not json", encoding="utf-8")

    exit_code = _run_main([
        "--config", str(bad_config),
        "--output", str(tmp_path / "results"),
    ])

    assert exit_code == 1
    assert not (tmp_path / "results").exists()


def test_empty_strategies_fails_via_cli(tmp_path):
    """An empty strategy list exits non-zero via the CLI."""
    dataset = _write_dataset(tmp_path)
    config_path = _write_config(tmp_path, dataset, strategies=[])

    exit_code = _run_main(["--config", str(config_path)])

    assert exit_code == 1
    assert not glob.glob(str(tmp_path / "results" / "run-*"))


# ============================================================================
# Entry point and online skip visibility (task 2.1)
# ============================================================================


def test_cli_help_entry_works():
    """The module entry point is importable and its help text is reachable."""
    import subprocess

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=repo_root,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert "--dataset" in result.stdout


def test_online_verification_skips_without_credentials():
    """Without credentials the online file skips visibly in pytest output."""
    import subprocess

    env = dict(os.environ)
    env.pop("SILICONFLOW_API_KEY", None)
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/test_online_verification.py",
            "-q", "--no-cov",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    summary_line = [ln for ln in result.stdout.splitlines() if ln.strip()][-1]
    assert "1 skipped" in summary_line
    assert "passed" not in summary_line


def test_missing_dataset_flag_reports_error(tmp_path, capsys):
    """`--dataset` pointing at a missing file reports the missing dataset."""
    missing = tmp_path / "nope-problems.json"

    from src.main import main

    exit_code = 0
    with patch("sys.argv", [
        "main.py",
        "--dataset", str(missing),
        "--output", str(tmp_path / "results"),
    ]):
        try:
            main()
        except SystemExit as exc:
            exit_code = exc.code or 0

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "nope-problems.json" in captured.err
    assert not (tmp_path / "results").exists()
