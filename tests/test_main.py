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
        )
        reports = {"vanilla": report1, "chain_of_thought": report2}

        print_report(reports)
        captured = capsys.readouterr()

        assert "vanilla" in captured.out
        assert "chain_of_thought" in captured.out
        assert "50.00%" in captured.out
        assert "80.00%" in captured.out


class TestSaveResults:
    """Test results saving function."""

    def test_save_results_creates_directory(self, tmp_path):
        """Test save_results creates output directory."""
        output_dir = tmp_path / "test_output"
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
        reports = {"vanilla": report}

        mock_harness = MagicMock()
        mock_harness.results = {"vanilla": []}

        save_results(reports, str(output_dir), mock_harness)

        assert output_dir.exists()

    def test_save_results_writes_summary(self, tmp_path):
        """Test save_results writes summary.json."""
        output_dir = tmp_path / "test_output"
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
        reports = {"vanilla": report}

        mock_harness = MagicMock()
        mock_harness.results = {"vanilla": []}

        save_results(reports, str(output_dir), mock_harness)

        summary_file = output_dir / "summary.json"
        assert summary_file.exists()

        with open(summary_file) as f:
            data = json.load(f)
            assert "strategies" in data
            assert "vanilla" in data["strategies"]

    def test_save_results_writes_detailed_results(self, tmp_path):
        """Test save_results writes detailed_results.json."""
        output_dir = tmp_path / "test_output"
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
        reports = {"vanilla": report}

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "problem_id": "test_1",
            "strategy": "vanilla",
            "success": True,
        }

        mock_harness = MagicMock()
        mock_harness.results = {"vanilla": [mock_result]}

        save_results(reports, str(output_dir), mock_harness)

        detailed_file = output_dir / "vanilla_results.json"
        assert detailed_file.exists()

        with open(detailed_file) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["problem_id"] == "test_1"


class TestMainExecution:
    """Test main function execution paths."""

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
