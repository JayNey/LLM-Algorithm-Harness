"""Benchmark suite data structures and loading."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class BenchmarkSuite(BaseModel):
    """
    A fixed benchmark suite for learning curve tracking.

    Attributes:
        name: Human-readable name of the benchmark suite
        problems: List of problem IDs to include
        frozen: Whether the suite is frozen (immutable)
        version: Version identifier for the suite
        description: Optional description of the suite
    """

    name: str = Field(..., description="Name of the benchmark suite")
    problems: list[str] = Field(..., min_length=1, description="List of problem IDs")
    frozen: bool = Field(default=True, description="Whether suite is frozen")
    version: str = Field(default="1.0", description="Version identifier")
    description: str | None = Field(None, description="Optional description")

    @field_validator("problems")
    @classmethod
    def validate_problems_non_empty(cls, v: list[str]) -> list[str]:
        """Ensure problems list is not empty."""
        if not v:
            raise ValueError("Benchmark suite must contain at least one problem")
        return v

    @field_validator("name")
    @classmethod
    def validate_name_non_empty(cls, v: str) -> str:
        """Ensure name is not empty."""
        if not v or not v.strip():
            raise ValueError("Benchmark suite name cannot be empty")
        return v.strip()


def load_benchmark_suite(config_path: str | Path) -> BenchmarkSuite:
    """
    Load a benchmark suite from a JSON configuration file.

    Args:
        config_path: Path to the benchmark.json configuration file

    Returns:
        Loaded BenchmarkSuite instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid
        json.JSONDecodeError: If config file is not valid JSON
    """
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Benchmark config not found: {config_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in benchmark config: {e}")

    try:
        return BenchmarkSuite.model_validate(data)
    except Exception as e:
        raise ValueError(f"Invalid benchmark suite configuration: {e}")
