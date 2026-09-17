"""
Unit tests for main.py module functions.

These tests directly invoke main.py functions to achieve coverage,
complementing the integration tests that use subprocess.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.main import create_default_config, load_config, print_report, save_results
from src.models import StrategyReport


class TestLoadConfig:
    """Test configuration loading function."""

    def test_load_config_valid_json(self):
        """Test loading valid JSON configuration."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "dataset_path": "data/test.json",
                "output_dir": "output",
                "llm_config": {
                    "provider": "openai",
                    "api_key": "test-key",
                    "model": "gpt-3.5-turbo",
                },
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)
            assert config.dataset_path == "data/test.json"
            assert config.output_dir == "output"
            assert config.llm_config.provider == "openai"
        finally:
            Path(config_path).unlink(missing_ok=True)

    def test_load_config_missing_file(self):
        """Test loading from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent_config.json")


class TestCreateDefaultConfig:
    """Test default configuration creation."""

    def test_create_default_config_basic(self):
        """Test creating default configuration with basic parameters."""
        config = create_default_config(
            dataset_path="data/problems.json", output_dir="output"
        )

        assert config.dataset_path == "data/problems.json"
        assert config.output_dir == "output"
        assert config.llm_config.provider == "openai"
        assert config.llm_config.model == "gpt-3.5-turbo"
        assert config.sandbox_config.timeout_seconds == 5

    def test_create_default_config_has_all_required_fields(self):
        """Test default config has all required fields."""
        config = create_default_config(
            dataset_path="data/test.json", output_dir="out"
        )

        assert hasattr(config, "dataset_path")
        assert hasattr(config, "output_dir")
        assert hasattr(config, "llm_config")
        assert hasattr(config, "sandbox_config")
        assert hasattr(config, "problem_filters")


class TestPrintReport:
    """Test report printing function."""

    def test_print_report_single_strategy(self, capsys):
        """Test printing report for single strategy."""
        report = StrategyReport(
            strategy_name="vanilla",
            total_problems=10,
            solved_problems=7,
            failed_problems=3,
            success_rate=0.70,
            avg_attempts_per_problem=1.5,
            total_tokens=5000,
            avg_tokens_per_problem=500.0,
            estimated_cost_usd=0.025,
            formal_evaluable_problems=4,
            formal_solved_problems=3,
            formal_success_rate=0.75,
            sample_only_problems=6,
        )
        reports = {"vanilla": report}

        print_report(reports)
        captured = capsys.readouterr()

        assert "vanilla" in captured.out
        assert "70.00%" in captured.out

    def test_print_report_multiple_strategies(self, capsys):
        """Test printing report for multiple strategies."""
        report1 = StrategyReport(
            strategy_name="vanilla",
            total_problems=10,
            solved_problems=5,
            failed_problems=5,
            success_rate=0.50,
            avg_attempts_per_problem=1.2,
            total_tokens=3000,
            avg_tokens_per_problem=300.0,
            estimated_cost_usd=0.015,
            formal_evaluable_problems=4,
            formal_solved_problems=3,
            formal_success_rate=0.75,
            sample_only_problems=6,
        )
        report2 = StrategyReport(
            strategy_name="chain_of_thought",
            total_problems=10,
            solved_problems=8,
            failed_problems=2,
            success_rate=0.80,
            avg_attempts_per_problem=1.8,
            total_tokens=8000,
            avg_tokens_per_problem=800.0,
            estimated_cost_usd=0.040,
            formal_evaluable_problems=8,
            formal_solved_problems=6,
            formal_success_rate=0.75,
            sample_only_problems=2,
        )
        reports = {"vanilla": report1, "chain_of_thought": report2}

        print_report(reports)
        captured = capsys.readouterr()

        assert "vanilla" in captured.out
        assert "chain_of_thought" in captured.out
        assert "50.00%" in captured.out
        assert "80.00%" in captured.out
        assert "Formal" in captured.out
        assert "3/4" in captured.out


class TestSaveResults:
    """Test results saving function."""

    def _make_reports(self):
        """Build a minimal reports dict for save_results tests."""
        report = StrategyReport(
            strategy_name="vanilla",
            total_problems=5,
            solved_problems=3,
            failed_problems=2,
            success_rate=0.60,
            avg_attempts_per_problem=1.3,
            total_tokens=2000,
            avg_tokens_per_problem=400.0,
            estimated_cost_usd=0.010,
        )
        return {"vanilla": report}

    def _run_save(self, tmp_path, results=None):
        """Call save_results with a real config; return the run directory."""
        output_dir = tmp_path / "test_output"
        mock_harness = MagicMock()
        mock_harness.results = {"vanilla": results or []}
        config = create_default_config("data/problems.json", str(output_dir))
        config.llm_config.api_key = "sk-test-secret"
        save_results(self._make_reports(), str(output_dir), mock_harness, config)
        with open(output_dir / "latest.json") as f:
            run_name = json.load(f)["latest_run"]
        return output_dir, output_dir / run_name

    def test_save_results_creates_directory(self, tmp_path):
        """Test save_results creates a timestamped run directory."""
        output_dir, run_dir = self._run_save(tmp_path)

        assert run_dir.exists()
        assert run_dir.parent == output_dir
        assert run_dir.name.startswith("run-")

    def test_save_results_writes_summary(self, tmp_path):
        """Test save_results writes summary.json inside the run directory."""
        _, run_dir = self._run_save(tmp_path)

        summary_file = run_dir / "summary.json"
        assert summary_file.exists()

        with open(summary_file) as f:
            data = json.load(f)
            assert "strategies" in data
            assert "vanilla" in data["strategies"]

    def test_save_results_writes_metadata_with_redacted_key(self, tmp_path):
        """Test save_results writes metadata.json and redacts the api key."""
        _, run_dir = self._run_save(tmp_path)

        metadata_file = run_dir / "metadata.json"
        assert metadata_file.exists()

        with open(metadata_file) as f:
            metadata = json.load(f)
        assert metadata["dataset_path"] == "data/problems.json"
        assert metadata["llm"]["model"] == "gpt-3.5-turbo"
        assert metadata["config"]["llm_config"]["api_key"] == "[REDACTED]"

    def test_save_results_writes_detailed_results(self, tmp_path):
        """Test save_results writes per-strategy detailed results in run dir."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "problem_id": "test_1",
            "strategy": "vanilla",
            "success": True,
        }

        _, run_dir = self._run_save(tmp_path, results=[mock_result])

        detailed_file = run_dir / "vanilla_results.json"
        assert detailed_file.exists()

        with open(detailed_file) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["problem_id"] == "test_1"

    def test_save_results_redacts_nested_credentials(self, tmp_path):
        """JSON snapshots sanitize nested fields and credential-shaped errors."""
        secret = "issue4-json-export-secret"
        output_dir = tmp_path / "test_output"
        report = MagicMock()
        report.model_dump.return_value = {
            "strategy_name": "vanilla",
            "metadata": {"api_key": secret},
        }
        result = MagicMock()
        result.model_dump.return_value = {
            "problem_id": "test_1",
            "error_message": f"Authorization: Bearer {secret}",
        }
        mock_harness = MagicMock()
        mock_harness.results = {"vanilla": [result]}
        config = create_default_config("data/problems.json", str(output_dir))
        config.llm_config.api_key = secret

        save_results({"vanilla": report}, str(output_dir), mock_harness, config)

        run_name = json.loads((output_dir / "latest.json").read_text())["latest_run"]
        run_dir = output_dir / run_name
        exported = (run_dir / "summary.json").read_text() + (
            run_dir / "vanilla_results.json"
        ).read_text()
        assert secret not in exported
        assert "[REDACTED]" in exported


class TestMainExecution:
    """Test main function execution paths."""

    @patch("src.main.setup_logging")
    @patch("src.main.AlgorithmHarness")
    def test_main_enables_redacting_logging(
        self, mock_harness_class, mock_setup_logging
    ):
        """The CLI activates the processor that redacts structured events."""
        mock_harness = MagicMock()
        mock_harness.run.return_value = {}
        mock_harness.results = {}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch("sys.argv", ["main.py", "--dataset", "data/problems.json"]):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        mock_setup_logging.assert_called_once()

    @patch("src.main.setup_logging")
    @patch("src.main.AlgorithmHarness")
    def test_main_passes_log_format_to_setup_logging(
        self, mock_harness_class, mock_setup_logging
    ):
        """--log-format reaches setup_logging so the console rendering switches."""
        mock_harness = MagicMock()
        mock_harness.run.return_value = {}
        mock_harness.results = {}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch("sys.argv", ["main.py", "--dataset", "data/problems.json", "--log-format", "json"]):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        mock_setup_logging.assert_called_once_with(console_format="json")

    @patch("src.main.setup_logging")
    @patch("src.main.AlgorithmHarness")
    def test_main_defaults_log_format_to_console(
        self, mock_harness_class, mock_setup_logging
    ):
        """Without --log-format the CLI activates the human-readable console."""
        mock_harness = MagicMock()
        mock_harness.run.return_value = {}
        mock_harness.results = {}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch("sys.argv", ["main.py", "--dataset", "data/problems.json"]):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        mock_setup_logging.assert_called_once_with(console_format="console")

    @patch("src.main.AlgorithmHarness")
    def test_main_uses_dataset_and_output_from_config_when_cli_omits_them(
        self, mock_harness_class, tmp_path
    ):
        """CLI defaults must not overwrite paths explicitly stored in the config file."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
dataset_path: data/from-config.json
output_dir: reports/from-config
llm_config:
  provider: openai
  api_key: test-key
  model: gpt-3.5-turbo
strategies:
  - name: vanilla
""",
            encoding="utf-8",
        )
        mock_harness = MagicMock()
        mock_harness.run.return_value = {}
        mock_harness.results = {}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch("sys.argv", ["main.py", "--config", str(config_path)]):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        resolved = mock_harness_class.call_args.args[0]
        assert resolved.dataset_path == "data/from-config.json"
        assert resolved.output_dir == "reports/from-config"

    @patch("src.main.AlgorithmHarness")
    def test_main_uses_program_output_default_when_config_omits_it(
        self, mock_harness_class, tmp_path
    ):
        """An omitted output directory falls back to the documented program default."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
dataset_path: data/from-config.json
llm_config:
  provider: openai
  api_key: test-key
  model: gpt-3.5-turbo
strategies:
  - name: vanilla
""",
            encoding="utf-8",
        )
        mock_harness = MagicMock()
        mock_harness.run.return_value = {}
        mock_harness.results = {}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch("sys.argv", ["main.py", "--config", str(config_path)]):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        resolved = mock_harness_class.call_args.args[0]
        assert resolved.output_dir == "./results"

    @patch("src.main.AlgorithmHarness")
    def test_explicit_cli_paths_override_config(self, mock_harness_class, tmp_path):
        """Explicit dataset and output arguments take precedence over file values."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "dataset_path": "data/from-config.json",
                    "output_dir": "reports/from-config",
                    "llm_config": {
                        "provider": "openai",
                        "api_key": "test-key",
                        "model": "gpt-3.5-turbo",
                    },
                    "strategies": [{"name": "vanilla"}],
                }
            ),
            encoding="utf-8",
        )
        mock_harness = MagicMock()
        mock_harness.run.return_value = {}
        mock_harness.results = {}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch(
            "sys.argv",
            [
                "main.py",
                "--config",
                str(config_path),
                "--dataset",
                "data/from-cli.json",
                "--output",
                "reports/from-cli",
            ],
        ):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        resolved = mock_harness_class.call_args.args[0]
        assert resolved.dataset_path == "data/from-cli.json"
        assert resolved.output_dir == "reports/from-cli"

    @patch("src.main.AlgorithmHarness")
    def test_cli_dataset_supplies_path_missing_from_config(self, mock_harness_class, tmp_path):
        """A CLI dataset satisfies the requirement even when the config omits it."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
llm_config:
  provider: openai
  api_key: test-key
  model: gpt-3.5-turbo
strategies:
  - name: vanilla
""",
            encoding="utf-8",
        )
        mock_harness = MagicMock()
        mock_harness.run.return_value = {}
        mock_harness.results = {}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch(
            "sys.argv",
            ["main.py", "--config", str(config_path), "--dataset", "data/from-cli.json"],
        ):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        resolved = mock_harness_class.call_args.args[0]
        assert resolved.dataset_path == "data/from-cli.json"

    @pytest.mark.parametrize("limit", ["0", "-1"])
    @patch("src.main.AlgorithmHarness")
    def test_main_rejects_non_positive_limit(self, mock_harness_class, limit):
        """A zero or negative limit must fail before the harness starts."""
        from src.main import main

        with patch("sys.argv", ["main.py", "--dataset", "data/problems.json", "--limit", limit]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        mock_harness_class.assert_not_called()

    @pytest.mark.parametrize(
        "strategies",
        [[], [{"name": "not_a_strategy"}]],
        ids=["empty", "unknown"],
    )
    @patch("src.main.AlgorithmHarness")
    def test_main_rejects_config_without_valid_strategies(
        self, mock_harness_class, tmp_path, strategies
    ):
        """Empty and unknown configured strategies must not create an empty evaluation."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "dataset_path": "data/problems.json",
                    "llm_config": {
                        "provider": "openai",
                        "api_key": "test-key",
                        "model": "gpt-3.5-turbo",
                    },
                    "strategies": strategies,
                }
            ),
            encoding="utf-8",
        )

        from src.main import main

        with patch("sys.argv", ["main.py", "--config", str(config_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_harness_class.assert_not_called()

    @patch("src.main.AlgorithmHarness")
    def test_main_rejects_selected_strategy_missing_from_config(self, mock_harness_class, tmp_path):
        """Selecting a valid built-in strategy absent from the config must fail clearly."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "dataset_path": "data/problems.json",
                    "llm_config": {
                        "provider": "openai",
                        "api_key": "test-key",
                        "model": "gpt-3.5-turbo",
                    },
                    "strategies": [{"name": "vanilla"}],
                }
            ),
            encoding="utf-8",
        )

        from src.main import main

        with patch(
            "sys.argv",
            ["main.py", "--config", str(config_path), "--strategy", "chain_of_thought"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_harness_class.assert_not_called()

    @patch("src.main.AlgorithmHarness")
    def test_main_rejects_non_positive_limit_from_config(self, mock_harness_class, tmp_path):
        """A non-positive limit in a configuration file must fail before evaluation."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
dataset_path: data/problems.json
llm_config:
  provider: openai
  api_key: test-key
  model: gpt-3.5-turbo
strategies:
  - name: vanilla
problem_filters:
  limit: 0
""",
            encoding="utf-8",
        )

        from src.main import main

        with patch("sys.argv", ["main.py", "--config", str(config_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_harness_class.assert_not_called()

    @patch("src.main.AlgorithmHarness")
    def test_explicit_cli_filters_override_only_matching_config_values(
        self, mock_harness_class, tmp_path
    ):
        """Difficulty and tags override file values while an omitted limit is preserved."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            """
dataset_path: data/problems.json
llm_config:
  provider: openai
  api_key: test-key
  model: gpt-3.5-turbo
strategies:
  - name: vanilla
problem_filters:
  difficulty: easy
  tags: [array]
  limit: 7
""",
            encoding="utf-8",
        )
        mock_harness = MagicMock()
        mock_harness.run.return_value = {}
        mock_harness.results = {}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch(
            "sys.argv",
            [
                "main.py",
                "--config",
                str(config_path),
                "--difficulty",
                "hard",
                "--tags",
                "graph",
                "dynamic-programming",
            ],
        ):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        filters = mock_harness_class.call_args.args[0].problem_filters
        assert filters == {
            "difficulty": "hard",
            "tags": ["graph", "dynamic-programming"],
            "limit": 7,
        }

    @patch("src.main.AlgorithmHarness")
    @patch("src.main.Path")
    def test_main_with_dataset_argument(self, mock_path_class, mock_harness_class):
        """Test main execution with dataset argument."""
        # Mock Path.exists to return True
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_class.return_value = mock_path_instance

        # Mock harness and report
        report = StrategyReport(
            strategy_name="vanilla",
            total_problems=1,
            solved_problems=1,
            failed_problems=0,
            success_rate=1.0,
            avg_attempts_per_problem=1.0,
            total_tokens=500,
            avg_tokens_per_problem=500.0,
            estimated_cost_usd=0.0025,
        )

        mock_harness = MagicMock()
        mock_harness.results = {"vanilla": []}
        mock_harness.get_report.return_value = {"vanilla": report}
        mock_harness_class.return_value = mock_harness

        from src.main import main

        with patch(
            "sys.argv", ["main.py", "--dataset", "data/sample_problems.json"]
        ):
            with patch("src.main.save_results"):
                with patch("src.main.print_report"):
                    main()

        mock_harness_class.assert_called_once()
        mock_harness.run.assert_called_once()

    @patch("src.main.sys.exit")
    @patch("src.main.logger")
    @patch("src.main.Path")
    def test_main_with_missing_dataset(self, mock_path, mock_logger, mock_exit):
        """Test main exits gracefully when dataset not found."""
        # Mock Path to indicate file doesn't exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path.return_value = mock_path_instance

        from src.main import main

        with patch("sys.argv", ["main.py", "--dataset", "nonexistent.json"]):
            main()

        # Should exit with error
        mock_exit.assert_called_with(1)

    @patch("src.main.AlgorithmHarness")
    def test_main_with_config_file(self, mock_harness_class):
        """Test main execution with config file."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            config_data = {
                "dataset_path": "data/sample_problems.json",
                "output_dir": "output",
                "llm_config": {
                    "provider": "openai",
                    "api_key": "test-key-123",
                    "model": "gpt-3.5-turbo",
                },
                "strategies": [{"name": "vanilla"}],
            }
            json.dump(config_data, f)
            config_path = f.name

        try:
            # Mock harness instance and report
            report = StrategyReport(
                strategy_name="vanilla",
                total_problems=0,
                solved_problems=0,
                failed_problems=0,
                success_rate=0.0,
                avg_attempts_per_problem=0.0,
                total_tokens=0,
                avg_tokens_per_problem=0.0,
                estimated_cost_usd=0.0,
            )

            mock_harness = MagicMock()
            mock_harness.results = {"vanilla": []}
            mock_harness.get_report.return_value = {"vanilla": report}
            mock_harness_class.return_value = mock_harness

            from src.main import main

            with patch(
                "sys.argv",
                [
                    "main.py",
                    "--dataset",
                    "data/sample_problems.json",
                    "--config",
                    config_path,
                ],
            ):
                with patch("src.main.Path") as mock_path:
                    mock_path.return_value.exists.return_value = True
                    with patch("src.main.save_results"):
                        with patch("src.main.print_report"):
                            main()

            # Verify harness was created and run
            mock_harness_class.assert_called_once()
            mock_harness.run.assert_called_once()

        finally:
            Path(config_path).unlink(missing_ok=True)

    def test_main_missing_required_arg(self):
        """Test main exits when required dataset argument is missing."""
        from src.main import main

        with patch("sys.argv", ["main.py"]):
            # ArgumentParser will raise SystemExit for missing required args
            with pytest.raises(SystemExit) as exc_info:
                main()
            # argparse exits with code 2 for usage errors
            assert exc_info.value.code == 2
