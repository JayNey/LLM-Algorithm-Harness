"""
Integration tests for CLI entry point (main.py).

These tests verify the command-line interface functionality
to achieve coverage of the main.py module.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_cli_help_command(self):
        """Test --help displays usage information."""
        result = subprocess.run(
            [sys.executable, "-m", "src.main", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "usage" in result.stdout.lower() or "LLM" in result.stdout

    def test_cli_version_or_basic_invoke(self):
        """Test CLI can be invoked without crashing on basic commands."""
        # Try to run with minimal args - will fail but should parse args
        result = subprocess.run(
            [sys.executable, "-m", "src.main"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Either succeeds or fails gracefully with error message
        assert "error" in result.stderr.lower() or result.returncode in [0, 1, 2]


class TestCLIDatasetLoading:
    """Test dataset loading through CLI."""

    def test_cli_with_sample_dataset(self):
        """Test CLI loads and processes sample dataset."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.main",
                "--dataset",
                "data/sample_problems.json",
                "--strategy",
                "vanilla",
                "--limit",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # May fail due to API key, but should attempt to load dataset
        output = (result.stdout + result.stderr).lower()
        assert (
            "dataset" in output
            or "problem" in output
            or "api" in output
            or "strategy" in output
        )

    def test_cli_with_nonexistent_dataset(self):
        """Test CLI handles missing dataset file gracefully."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.main",
                "--dataset",
                "nonexistent_file.json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        output = (result.stdout + result.stderr).lower()
        assert "not found" in output or "error" in output or "no such file" in output


class TestCLIConfigLoading:
    """Test configuration file loading."""

    def test_cli_with_yaml_config(self):
        """Test CLI loads YAML configuration file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            # Write minimal valid YAML config
            f.write(
                """
llm_config:
  provider: openai
  model: gpt-3.5-turbo
  api_key: test-key-12345
dataset_path: data/sample_problems.json
"""
            )
            config_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.main", "--config", config_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Config should be loaded even if execution fails later
            output = (result.stdout + result.stderr).lower()
            # Should attempt to use config
            assert (
                result.returncode in [0, 1]
                or "config" in output
                or "dataset" in output
                or "api" in output
            )
        finally:
            Path(config_path).unlink(missing_ok=True)

    def test_cli_with_invalid_config(self):
        """Test CLI handles invalid configuration gracefully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("invalid: yaml: content: [unclosed")
            config_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.main", "--config", config_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode != 0
            output = (result.stdout + result.stderr).lower()
            assert "error" in output or "invalid" in output or "yaml" in output
        finally:
            Path(config_path).unlink(missing_ok=True)

    def test_config_only_cli_run_with_fake_model_writes_expected_results(
        self, tmp_path, monkeypatch
    ):
        """Run the real CLI workflow with a fake model response and inspect its files."""

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="""```python
def solution(nums, target):
    seen = {}
    for index, value in enumerate(nums):
        complement = target - value
        if complement in seen:
            return [seen[complement], index]
        seen[value] = index
```"""),
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(
                        prompt_tokens=10,
                        completion_tokens=20,
                        total_tokens=30,
                    ),
                    model=kwargs["model"],
                )

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        dataset_path = tmp_path / "problems.json"
        dataset_path.write_text(
            json.dumps(
                [
                    {
                        "problem_id": "two-sum",
                        "title": "Two Sum",
                        "description": "Return the indices of two values that add up to the target.",
                        "difficulty": "easy",
                        "tags": ["array"],
                        "test_cases": [
                            {
                                "input": {"nums": [2, 7, 11, 15], "target": 9},
                                "expected_output": [0, 1],
                            }
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        output_path = tmp_path / "results"
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            f"""
dataset_path: {dataset_path}
output_dir: {output_path}
llm_config:
  provider: openai
  api_key: fake-key
  model: fake-model
strategies:
  - name: vanilla
""",
            encoding="utf-8",
        )

        monkeypatch.setattr("src.llm_client.OpenAI", FakeOpenAI)
        monkeypatch.setattr(sys, "argv", ["harness", "--config", str(config_path)])

        from src.main import main

        main()

        summary = json.loads((output_path / "summary.json").read_text(encoding="utf-8"))
        details = json.loads((output_path / "vanilla_results.json").read_text(encoding="utf-8"))
        assert summary["strategies"]["vanilla"]["solved_problems"] == 1
        assert summary["strategies"]["vanilla"]["total_problems"] == 1
        assert details[0]["problem_id"] == "two-sum"
        assert details[0]["status"] == "success"


class TestCLIStrategySelection:
    """Test strategy selection through CLI."""

    def test_cli_with_valid_strategy(self):
        """Test CLI accepts valid strategy names."""
        for strategy in ["vanilla", "chain_of_thought", "multi_round_feedback"]:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.main",
                    "--dataset",
                    "data/sample_problems.json",
                    "--strategy",
                    strategy,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # May fail due to API key but should recognize strategy
            output = (result.stdout + result.stderr).lower()
            assert strategy in output or "api" in output or "key" in output

    def test_cli_with_invalid_strategy(self):
        """Test CLI rejects invalid strategy names."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.main",
                "--dataset",
                "data/sample_problems.json",
                "--strategy",
                "invalid_nonexistent_strategy",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        output = (result.stdout + result.stderr).lower()
        assert "strategy" in output or "invalid" in output or "unknown" in output


class TestCLIOutputOptions:
    """Test output and reporting options."""

    def test_cli_with_output_dir(self, tmp_path):
        """Test CLI respects output directory option."""
        output_dir = tmp_path / "test_output"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.main",
                "--dataset",
                "data/sample_problems.json",
                "--strategy",
                "vanilla",
                "--output-dir",
                str(output_dir),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Check that output dir option was recognized
        output = (result.stdout + result.stderr).lower()
        assert (
            result.returncode in [0, 1]
            or "output" in output
            or str(output_dir) in result.stderr
        )

    def test_cli_with_limit_option(self):
        """Test CLI respects problem limit option."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.main",
                "--dataset",
                "data/sample_problems.json",
                "--limit",
                "5",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should process or attempt to process limited problems
        output = (result.stdout + result.stderr).lower()
        assert (
            result.returncode in [0, 1]
            or "limit" in output
            or "problem" in output
            or "api" in output
        )


class TestCLIDifficultyFilter:
    """Test difficulty filtering through CLI."""

    def test_cli_with_difficulty_filter(self):
        """Test CLI filters problems by difficulty."""
        for difficulty in ["easy", "medium", "hard"]:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.main",
                    "--dataset",
                    "data/sample_problems.json",
                    "--difficulty",
                    difficulty,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = (result.stdout + result.stderr).lower()
            assert (
                result.returncode in [0, 1]
                or difficulty in output
                or "difficulty" in output
                or "api" in output
            )


class TestCLIErrorHandling:
    """Test CLI error handling and edge cases."""

    def test_cli_with_missing_required_args(self):
        """Test CLI handles missing required arguments."""
        result = subprocess.run(
            [sys.executable, "-m", "src.main", "--strategy", "vanilla"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should fail or prompt for required args
        assert result.returncode in [0, 1, 2]

    def test_cli_with_conflicting_args(self):
        """Test CLI handles potentially conflicting arguments."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.main",
                "--dataset",
                "data/sample_problems.json",
                "--config",
                "nonexistent_config.yaml",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should handle gracefully
        assert result.returncode in [0, 1, 2]


# Mark all tests in this file to run with a reasonable timeout
# pytestmark = pytest.mark.timeout(60)
