"""Tests for utility modules."""

import json
import logging as std_logging
import uuid

import pytest
import yaml

import structlog

import src.utils.logging as logging_utils
from src.utils.logging import get_logger, setup_logging

from src.utils.config import (
    get_default_config,
    load_config,
    merge_configs,
    validate_config,
)
from src.utils.validators import (
    validate_file_path,
    validate_problem_schema,
    validate_strategy_name,
    validate_test_case,
)

# ============================================================================
# Config Utils Tests
# ============================================================================


def test_structured_log_processor_redacts_nested_credentials():
    """Structured event dictionaries are sanitized before rendering."""
    assert hasattr(logging_utils, "redact_sensitive_event")
    secret = "issue4-structured-log-secret"
    event = {
        "event": "provider_failed",
        "config": {"llm_config": {"api_key": secret}},
        "error": f"Authorization: Bearer {secret}",
    }

    redacted = logging_utils.redact_sensitive_event(None, None, event)

    assert secret not in str(redacted)
    assert redacted["config"]["llm_config"]["api_key"] == "[REDACTED]"


def test_get_default_config():
    """Test getting default configuration."""
    config = get_default_config()

    assert "llm_config" in config
    assert "output_dir" in config
    assert config["llm_config"]["provider"] == "openai"
    assert config["max_workers"] == 5


def test_load_config_valid(tmp_path):
    """Test loading valid configuration file."""
    config_file = tmp_path / "config.yaml"
    config_data = {
        "llm_config": {
            "provider": "openai",
            "api_key": "test-key",
            "model": "gpt-3.5-turbo",
        },
        "dataset_path": "data/problems.json",
        "output_dir": "output/",
        "max_workers": 5,
    }
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    assert config.llm_config.provider == "openai"
    assert config.max_workers == 5
    assert config.dataset_path == "data/problems.json"


def test_load_config_valid_json(tmp_path):
    """JSON remains supported through the shared configuration loader."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "llm_config": {
                    "provider": "openai",
                    "api_key": "test-key",
                    "model": "gpt-3.5-turbo",
                },
                "dataset_path": "data/from-json.json",
                "strategies": [{"name": "vanilla"}],
            }
        ),
        encoding="utf-8",
    )

    config = load_config(str(config_file))

    assert config.dataset_path == "data/from-json.json"
    assert [strategy.name for strategy in config.strategies] == ["vanilla"]


@pytest.mark.parametrize("content", ["", "- not\n- a\n- mapping\n"])
def test_load_config_rejects_non_mapping_document(tmp_path, content):
    """Empty and sequence documents fail with a configuration-specific error."""
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="mapping"):
        load_config(str(config_file))


def test_load_config_not_found():
    """Test loading non-existent config file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config("/path/does/not/exist.yaml")


def test_merge_configs():
    """Test merging multiple configuration layers."""
    default = {"a": 1, "b": {"x": 10, "y": 20}, "c": 3}
    user = {"b": {"y": 25, "z": 30}, "d": 4}
    env = {"a": 2, "e": 5}

    merged = merge_configs(default, user, env)

    assert merged["a"] == 2  # env override
    assert merged["b"]["x"] == 10  # from default
    assert merged["b"]["y"] == 25  # from user
    assert merged["b"]["z"] == 30  # from user
    assert merged["c"] == 3  # from default
    assert merged["d"] == 4  # from user
    assert merged["e"] == 5  # from env


def test_validate_config_valid():
    """Test validating valid configuration."""
    config = {
        "llm_config": {"provider": "openai", "api_key": "test", "model": "gpt-3.5-turbo"},
        "output_dir": "output/",
    }

    assert validate_config(config) is True


def test_validate_config_missing_key():
    """Test validation fails for missing required key."""
    config = {
        "output_dir": "output/",
        # Missing llm_config
    }

    with pytest.raises(ValueError, match="Missing required configuration key"):
        validate_config(config)


def test_validate_config_missing_llm_key():
    """Test validation fails for missing LLM config key."""
    config = {
        "llm_config": {
            "provider": "openai",
            # Missing api_key and model
        },
        "output_dir": "output/",
    }

    with pytest.raises(ValueError, match="Missing required LLM config key"):
        validate_config(config)


# ============================================================================
# Validators Tests
# ============================================================================


def test_validate_problem_schema_valid():
    """Test validating valid problem schema."""
    data = {
        "problem_id": "test-001",
        "title": "Test Problem",
        "description": "Test description",
        "difficulty": "easy",
        "test_cases": [{"input": {}, "expected_output": None}],
    }

    assert validate_problem_schema(data) is True


def test_validate_problem_schema_missing_field():
    """Test validation fails for missing required field."""
    data = {
        "problem_id": "test-001",
        # Missing title
        "description": "Test description",
        "difficulty": "easy",
        "test_cases": [],
    }

    with pytest.raises(ValueError, match="Missing required field"):
        validate_problem_schema(data)


def test_validate_problem_schema_invalid_difficulty():
    """Test validation fails for invalid difficulty."""
    data = {
        "problem_id": "test-001",
        "title": "Test",
        "description": "Description",
        "difficulty": "超难",  # Invalid
        "test_cases": [{}],
    }

    with pytest.raises(ValueError, match="Invalid difficulty"):
        validate_problem_schema(data)


def test_validate_problem_schema_empty_test_cases():
    """Test validation fails for empty test_cases."""
    data = {
        "problem_id": "test-001",
        "title": "Test",
        "description": "Description",
        "difficulty": "easy",
        "test_cases": [],  # Empty
    }

    with pytest.raises(ValueError, match="non-empty list"):
        validate_problem_schema(data)


def test_validate_test_case_valid():
    """Test validating valid test case."""
    test_case = {"input": {"x": 1}, "expected_output": 2}

    assert validate_test_case(test_case) is True


def test_validate_stdin_test_case_accepts_raw_text():
    """stdin/stdout test cases may use raw input strings."""
    assert validate_test_case(
        {"input": "2 3\n", "expected_output": "5\n"},
        input_output_mode="stdin_stdout",
    ) is True


def test_validate_test_case_missing_input():
    """Test validation fails for missing input."""
    test_case = {"expected_output": 2}

    with pytest.raises(ValueError, match="missing 'input'"):
        validate_test_case(test_case)


def test_validate_test_case_missing_expected_output():
    """Test validation fails for missing expected_output."""
    test_case = {"input": {"x": 1}}

    with pytest.raises(ValueError, match="missing 'expected_output'"):
        validate_test_case(test_case)


def test_validate_test_case_input_not_dict():
    """Test validation fails when input is not a dict."""
    test_case = {"input": [1, 2, 3], "expected_output": 2}

    with pytest.raises(ValueError, match="must be a dictionary"):
        validate_test_case(test_case)


def test_validate_file_path_exists(tmp_path):
    """Test validating existing file path."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test")

    assert validate_file_path(str(file_path), must_exist=True) is True


def test_validate_file_path_not_exists():
    """Test validation fails for non-existent file."""
    with pytest.raises(FileNotFoundError):
        validate_file_path("/path/does/not/exist.txt", must_exist=True)


def test_validate_file_path_not_exists_optional():
    """Test validation succeeds for non-existent file when must_exist=False."""
    assert validate_file_path("/path/does/not/exist.txt", must_exist=False) is True


def test_validate_file_path_empty():
    """Test validation fails for empty path."""
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_file_path("")


def test_validate_strategy_name_valid():
    """Test validating valid strategy names."""
    assert validate_strategy_name("vanilla") is True
    assert validate_strategy_name("chain_of_thought") is True
    assert validate_strategy_name("multi-round-feedback") is True
    assert validate_strategy_name("cot_v2") is True


def test_validate_strategy_name_empty():
    """Test validation fails for empty name."""
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_strategy_name("")


def test_validate_strategy_name_invalid_chars():
    """Test validation fails for invalid characters."""
    with pytest.raises(ValueError, match="alphanumeric"):
        validate_strategy_name("invalid name!")

    with pytest.raises(ValueError, match="alphanumeric"):
        validate_strategy_name("invalid/name")


# ============================================================================
# Console logging format tests (readable-console-logs)
# ============================================================================


@pytest.fixture
def fresh_logging():
    """Reset logging state around each test so runs stay independent."""
    root = std_logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    noisy_levels = {
        name: std_logging.getLogger(name).level
        for name in ("httpx", "httpx2", "httpcore", "openai")
    }
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for name, level in noisy_levels.items():
        std_logging.getLogger(name).setLevel(level)
    structlog.reset_defaults()


def test_console_format_renders_human_readable(fresh_logging, capsys):
    """Default console mode emits readable key=value lines, not JSON."""
    setup_logging(level="INFO", console_format="console")
    get_logger(f"probe-console-{uuid.uuid4().hex}").info("probe_event", problem_id="two-sum")

    out = capsys.readouterr().out
    assert "probe_event" in out
    assert "two-sum" in out
    assert not out.strip().startswith("{")


def test_json_format_keeps_machine_readable(fresh_logging, capsys):
    """Explicit json mode preserves the existing machine-readable output."""
    import json as json_lib

    setup_logging(level="INFO", console_format="json")
    get_logger(f"probe-json-{uuid.uuid4().hex}").info("probe_event", problem_id="two-sum")

    out = capsys.readouterr().out
    parsed = json_lib.loads(out.strip().splitlines()[-1])
    assert parsed["event"] == "probe_event"
    assert parsed["problem_id"] == "two-sum"


def test_console_format_redacts_credentials(fresh_logging, capsys):
    """Redaction applies to console output as well."""
    setup_logging(level="INFO", console_format="console")
    get_logger(f"probe-redact-{uuid.uuid4().hex}").info("cfg", api_key="sk-secret-123")

    out = capsys.readouterr().out
    assert "sk-secret-123" not in out
    assert "[REDACTED]" in out


def test_invalid_console_format_rejected(fresh_logging):
    """Unknown formats fail fast instead of silently falling back."""
    with pytest.raises(ValueError):
        setup_logging(level="INFO", console_format="yaml")


def test_third_party_noise_suppressed(fresh_logging):
    """httpx/httpx2/httpcore/openai request logs no longer flood the console."""
    setup_logging(level="INFO", console_format="console")
    for name in ("httpx", "httpx2", "httpcore", "openai"):
        assert std_logging.getLogger(name).level == std_logging.WARNING


def test_repeat_setup_switches_format_for_bound_logger(fresh_logging, capsys):
    """Re-calling setup_logging switches rendering even for already-used loggers."""
    setup_logging(level="INFO", console_format="json")
    log = get_logger("probe-rebind")
    log.info("first_event")

    setup_logging(level="INFO", console_format="console")
    log.info("second_event")

    lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln.strip()]
    assert len(lines) == 2
    assert lines[0].startswith("{")
    assert "second_event" in lines[1]
    assert not lines[1].startswith("{")
