"""
Unit tests for CSVExporter.
"""

import csv
from pathlib import Path
from typing import List

import pytest

from src.models import ExecutionResult, TestCaseResult, SandboxResult, IterationResult
from src.reporting.csv_exporter import CSVExporter


@pytest.fixture
def temp_csv_path(tmp_path: Path) -> str:
    """Fixture for temporary CSV file path."""
    return str(tmp_path / "test_export.csv")


@pytest.fixture
def sample_execution_result() -> ExecutionResult:
    """Fixture for sample execution result."""
    return ExecutionResult(
        problem_id="two_sum",
        strategy="direct",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(
                iteration=1,
                prompt_tokens=100,
                completion_tokens=50,
                code_extracted="def solution(): pass",
                sandbox_result=SandboxResult(
                    status="success",
                    test_results=[],
                    execution_time=0.1,
                    all_passed=True
                )
            )
        ],
        final_result=SandboxResult(
            status="success",
            test_results=[
                TestCaseResult(
                    test_case_index=0,
                    passed=True,
                    actual_output=[0, 1],
                    expected_output=[0, 1],
                    execution_time=0.01,
                    status="passed"
                )
            ],
            execution_time=0.1,
            all_passed=True
        ),
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.01,
                status="passed"
            )
        ],
        total_tokens=150,
        execution_time_seconds=0.5
    )


@pytest.fixture
def sample_failed_result() -> ExecutionResult:
    """Fixture for sample failed execution result."""
    return ExecutionResult(
        problem_id="three_sum",
        strategy="direct",
        generated_code="def solution(): pass",
        status="failed",
        iterations=[],
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=False,
                actual_output=[],
                expected_output=[0, 1, 2],
                execution_time=0.01,
                status="failed",
                error_message="Assertion failed"
            )
        ],
        error_message="Test failed",
        total_tokens=100,
        execution_time_seconds=0.2
    )


def test_export_empty_list(temp_csv_path: str):
    """Test exporting empty results list creates CSV with headers."""
    CSVExporter.export([], temp_csv_path)

    assert Path(temp_csv_path).exists()

    with open(temp_csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows = list(reader)

    expected_headers = [
        "problem_id", "strategy", "status", "passed", "tokens",
        "time", "iterations", "error_message", "total_tests",
        "passed_tests", "failed_tests"
    ]
    assert headers == expected_headers
    assert len(rows) == 0


def test_export_single_strategy(temp_csv_path: str, sample_execution_result: ExecutionResult):
    """Test exporting single strategy results."""
    results = [sample_execution_result]
    CSVExporter.export(results, temp_csv_path)

    assert Path(temp_csv_path).exists()

    with open(temp_csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    assert row['problem_id'] == 'two_sum'
    assert row['strategy'] == 'direct'
    assert row['status'] == 'success'
    assert row['passed'] == 'True'
    assert row['tokens'] == '150'
    assert row['iterations'] == '1'
    assert row['total_tests'] == '1'
    assert row['passed_tests'] == '1'
    assert row['failed_tests'] == '0'


def test_export_multiple_results(
    temp_csv_path: str,
    sample_execution_result: ExecutionResult,
    sample_failed_result: ExecutionResult
):
    """Test exporting multiple results."""
    results = [sample_execution_result, sample_failed_result]
    CSVExporter.export(results, temp_csv_path)

    with open(temp_csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2
    assert rows[0]['status'] == 'success'
    assert rows[1]['status'] == 'failed'
    assert rows[1]['error_message'] == 'Test failed'


def test_export_special_characters(temp_csv_path: str):
    """Test CSV escaping with special characters (commas, quotes, newlines)."""
    result = ExecutionResult(
        problem_id='test,problem',
        strategy='test"strategy',
        generated_code='def solution():\n    pass',
        status="success",
        iterations=[],
        test_results=[],
        error_message='Error with "quotes" and,commas\nand newlines',
        total_tokens=100,
        execution_time_seconds=0.1
    )

    CSVExporter.export([result], temp_csv_path)

    with open(temp_csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    assert row['problem_id'] == 'test,problem'
    assert row['strategy'] == 'test"strategy'
    assert 'quotes' in row['error_message']
    assert 'commas' in row['error_message']


def test_export_all_multiple_strategies(
    temp_csv_path: str,
    sample_execution_result: ExecutionResult,
    sample_failed_result: ExecutionResult
):
    """Test export_all merges multiple strategies correctly."""
    results_dict = {
        "strategy_a": [sample_execution_result],
        "strategy_b": [sample_failed_result]
    }

    CSVExporter.export_all(results_dict, temp_csv_path)

    with open(temp_csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2
    strategies = {row['strategy'] for row in rows}
    assert 'direct' in strategies


def test_export_creates_parent_directories(tmp_path: Path, sample_execution_result: ExecutionResult):
    """Test export creates parent directories if they don't exist."""
    nested_path = tmp_path / "reports" / "subdir" / "test.csv"
    CSVExporter.export([sample_execution_result], str(nested_path))

    assert nested_path.exists()
    assert nested_path.parent.exists()


def test_export_utf8_bom_encoding(temp_csv_path: str, sample_execution_result: ExecutionResult):
    """Test CSV is saved with UTF-8 BOM for Excel compatibility."""
    CSVExporter.export([sample_execution_result], temp_csv_path)

    # Read raw bytes to check BOM
    with open(temp_csv_path, 'rb') as f:
        first_bytes = f.read(3)

    # UTF-8 BOM is EF BB BF
    assert first_bytes == b'\xef\xbb\xbf'


def test_export_redacts_credentials_in_errors(
    temp_csv_path: str, sample_failed_result: ExecutionResult
):
    """CSV output cannot expose credential text from an error message."""
    secret = "issue4-csv-export-secret"
    sample_failed_result.error_message = f"request failed with api_key={secret}"

    CSVExporter.export([sample_failed_result], temp_csv_path)

    content = Path(temp_csv_path).read_text(encoding="utf-8-sig")
    assert secret not in content
    assert "[REDACTED]" in content
