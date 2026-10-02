"""
Historical run record management for incremental evaluation.
"""

import fcntl
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RunRecord:
    """Record of a single evaluation run for incremental matching."""

    run_id: str
    timestamp: str
    strategy: str
    model: str
    dataset_fingerprint: dict[str, str]
    result_path: str
    problem_count: int
    success_count: int


@dataclass
class IncrementalHistory:
    """Collection of historical run records for incremental evaluation."""

    runs: list[RunRecord]

    @classmethod
    def load(cls, path: Path) -> "IncrementalHistory":
        """
        Load incremental history from file.

        Creates an empty history if the file does not exist.
        Handles JSON parsing errors gracefully.

        Args:
            path: Path to history.json file

        Returns:
            IncrementalHistory instance (empty if file doesn't exist or is invalid)
        """
        if not path.exists():
            logger.info(f"History file not found at {path}, creating empty history")
            return cls(runs=[])

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            # Reconstruct RunRecord instances from dict
            runs = [RunRecord(**record) for record in data.get("runs", [])]
            return cls(runs=runs)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse history file {path}: {e}")
            return cls(runs=[])
        except (TypeError, KeyError) as e:
            logger.error(f"Invalid history file structure in {path}: {e}")
            return cls(runs=[])

    def save(self, path: Path, max_retries: int = 3) -> None:
        """
        Save history to file with file locking to prevent concurrent write conflicts.

        Args:
            path: Path to history.json file
            max_retries: Maximum number of retry attempts on lock failure

        Raises:
            IOError: If file cannot be written after retries
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {"runs": [asdict(record) for record in self.runs]}

        # Retry logic for file locking
        for attempt in range(max_retries):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    # Acquire exclusive lock
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        json.dump(data, f, indent=2)
                        f.write("\n")  # Trailing newline
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                logger.debug(f"Successfully saved history to {path}")
                return
            except OSError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Failed to acquire lock on {path} (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                else:
                    logger.error(f"Failed to save history after {max_retries} attempts: {e}")
                    raise

    def add_run(self, record: RunRecord) -> None:
        """
        Append a new run record to the history.

        Args:
            record: RunRecord to add
        """
        self.runs.append(record)
