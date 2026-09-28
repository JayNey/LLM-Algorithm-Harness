"""Benchmark suite manager for managing multiple suites."""

from pathlib import Path
from typing import Any

from src.benchmark.suite import BenchmarkSuite, load_benchmark_suite
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BenchmarkManager:
    """
    Manager for benchmark suites.

    Handles loading, listing, and validating benchmark suites.
    """

    def __init__(self, benchmark_dir: str | Path = "."):
        """
        Initialize benchmark manager.

        Args:
            benchmark_dir: Directory to search for benchmark configuration files
        """
        self.benchmark_dir = Path(benchmark_dir)
        self._suites: dict[str, BenchmarkSuite] = {}

    def load_suite(self, config_path: str | Path) -> BenchmarkSuite:
        """
        Load a benchmark suite from configuration file.

        Args:
            config_path: Path to benchmark configuration file

        Returns:
            Loaded BenchmarkSuite

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        try:
            suite = load_benchmark_suite(config_path)
            self._suites[suite.name] = suite
            logger.info("benchmark_suite_loaded", name=suite.name, problems=len(suite.problems))
            return suite
        except FileNotFoundError as e:
            logger.error("benchmark_config_not_found", path=str(config_path))
            raise
        except ValueError as e:
            logger.error("benchmark_config_invalid", path=str(config_path), error=str(e))
            raise

    def list_suites(self) -> list[str]:
        """
        List all available benchmark suite configuration files.

        Returns:
            List of paths to benchmark configuration files
        """
        suite_files = []

        # Search for benchmark*.json files
        for pattern in ["benchmark.json", "benchmark.*.json", "benchmark*.json"]:
            suite_files.extend(self.benchmark_dir.glob(pattern))

        return sorted([str(f) for f in suite_files])

    def get_suite(self, name: str) -> BenchmarkSuite | None:
        """
        Get a loaded suite by name.

        Args:
            name: Name of the benchmark suite

        Returns:
            BenchmarkSuite if found, None otherwise
        """
        return self._suites.get(name)

    def load_all_suites(self) -> dict[str, BenchmarkSuite]:
        """
        Load all available benchmark suites from the benchmark directory.

        Returns:
            Dictionary mapping suite names to BenchmarkSuite objects
        """
        suite_files = self.list_suites()

        loaded_suites = {}
        for suite_file in suite_files:
            try:
                suite = self.load_suite(suite_file)
                loaded_suites[suite.name] = suite
            except (FileNotFoundError, ValueError) as e:
                logger.warning("failed_to_load_suite", path=suite_file, error=str(e))
                continue

        return loaded_suites
