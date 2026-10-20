"""Unit tests for LOG_LEVEL / LOG_FORMAT logging assembly (issue #159)."""

import json
import logging

import pytest

from api.logging_config import JsonLineFormatter, configure_api_logging


@pytest.fixture()
def restore_logging():
    """Snapshot and restore the logging state the assembly mutates."""

    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    uvicorn_names = ("uvicorn", "uvicorn.error", "uvicorn.access")
    saved_uv = [
        (n, logging.getLogger(n).handlers[:], logging.getLogger(n).propagate) for n in uvicorn_names
    ]
    try:
        yield
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        for name, handlers, propagate in saved_uv:
            uv_logger = logging.getLogger(name)
            uv_logger.handlers[:] = handlers
            uv_logger.propagate = propagate


class TestConfigureApiLogging:
    def test_noop_by_default_under_pytest(self, restore_logging, monkeypatch):
        """Default ``enabled=None`` skips assembly so suites keep their capture handlers."""

        called = []
        monkeypatch.setattr(
            "src.utils.logging.setup_logging", lambda **kwargs: called.append(kwargs)
        )
        configure_api_logging()
        assert called == []

    def test_disabled_is_noop(self, restore_logging, monkeypatch):
        called = []
        monkeypatch.setattr(
            "src.utils.logging.setup_logging", lambda **kwargs: called.append(kwargs)
        )
        configure_api_logging(enabled=False)
        assert called == []

    def test_invalid_format_raises(self, restore_logging):
        with pytest.raises(ValueError, match="Unsupported LOG_FORMAT"):
            configure_api_logging(enabled=True, fmt="yaml")

    def test_invalid_level_raises(self, restore_logging):
        with pytest.raises(ValueError, match="Unsupported LOG_LEVEL"):
            configure_api_logging(enabled=True, level="verbose")

    def test_create_app_wires_logging_assembly(self, restore_logging, monkeypatch):
        """create_app 必须接线日志装配，删除接线时此用例失败。"""
        import api.main as main_module

        calls = []
        monkeypatch.setattr(main_module, "configure_api_logging", lambda *a, **k: calls.append(1))
        main_module.create_app()
        assert calls, "create_app 未调用 configure_api_logging"

    def test_text_mode_uses_console_renderer(self, restore_logging):
        configure_api_logging(enabled=True, level="warning", fmt="text")
        root = logging.getLogger()
        assert root.level == logging.WARNING
        assert not any(isinstance(h.formatter, JsonLineFormatter) for h in root.handlers)

    def test_json_mode_wraps_uvicorn_through_root(self, restore_logging):
        """uvicorn handlers are detached and root gets the JSON line formatter."""

        uv_access = logging.getLogger("uvicorn.access")
        uv_access.addHandler(logging.NullHandler())
        uv_access.propagate = False

        configure_api_logging(enabled=True, level="info", fmt="json")

        root = logging.getLogger()
        assert root.level == logging.INFO
        assert any(isinstance(h.formatter, JsonLineFormatter) for h in root.handlers)
        assert uv_access.handlers == []
        assert uv_access.propagate is True

    def test_switching_back_to_text_restores_formatter(self, restore_logging):
        configure_api_logging(enabled=True, fmt="json")
        configure_api_logging(enabled=True, fmt="text")
        root = logging.getLogger()
        assert not any(isinstance(h.formatter, JsonLineFormatter) for h in root.handlers)


class TestJsonLineFormatter:
    def _record(self, message: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=message,
            args=(),
            exc_info=None,
        )

    def test_structlog_json_passes_through(self):
        """Pre-rendered structlog objects are not double-wrapped."""

        event = json.dumps(
            {"timestamp": "2026-10-20T00:00:00+00:00", "level": "info", "event": "hi"}
        )
        formatted = JsonLineFormatter().format(self._record(event))
        assert json.loads(formatted) == json.loads(event)

    def test_plain_record_is_wrapped(self):
        formatted = JsonLineFormatter().format(self._record("GET /api/v1/health 200"))
        payload = json.loads(formatted)
        assert payload["event"] == "GET /api/v1/health 200"
        assert payload["level"] == "info"
        assert payload["logger"] == "uvicorn.access"
        assert "timestamp" in payload

    def test_plain_record_with_exception(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys

            record = self._record("crashed")
            record.exc_info = sys.exc_info()
        payload = json.loads(JsonLineFormatter().format(record))
        assert "RuntimeError" in payload["exception"]

    def test_non_dict_json_is_wrapped(self):
        formatted = JsonLineFormatter().format(self._record("42"))
        payload = json.loads(formatted)
        assert payload["event"] == "42"
