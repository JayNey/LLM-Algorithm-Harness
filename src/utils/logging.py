"""
Logging utilities for structured logging.
"""

import logging
import sys

import structlog

from src.utils.secrets import redact_sensitive_data


def redact_sensitive_event(logger, method_name, event_dict):
    """Structlog processor that recursively removes credentials."""
    return redact_sensitive_data(event_dict)


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    console_format: str = "console",
) -> None:
    """
    Initialize structured logging system.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        console_format: Terminal rendering, "console" for human-readable
            key=value lines or "json" for machine-readable JSON lines
    """
    if console_format not in ("console", "json"):
        raise ValueError(f"Unsupported console format: {console_format}")

    is_json = console_format == "json"
    renderer = (
        structlog.processors.JSONRenderer()
        if is_json
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso" if is_json else "%H:%M:%S"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            redact_sensitive_event,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging; force rebinds the stream when handlers
    # already exist (repeat calls, test harnesses, host plugins)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
        force=True,
    )

    # Third-party request logs (HTTP lines, retry chatter) drown the console;
    # harness events such as llm_api_error carry the useful signal.
    # httpx2 is the next-generation client used by openai>=3
    for noisy_logger in ("httpx", "httpx2", "httpcore", "openai"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        logging.getLogger().addHandler(file_handler)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a logger instance.

    Args:
        name: Logger name (usually module name)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)
