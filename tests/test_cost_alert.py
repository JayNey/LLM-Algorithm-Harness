"""Delivery, persistence, and secret-safety tests for cost alerts."""

import json
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from src.cost_alert import CostAlertManager
from src.models import CostAlertConfig, HarnessConfig, LLMConfig


class Response:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                "provider error with secret URL in message",
                response=self,
            )


def test_threshold_crossing_is_exact_durable_and_idempotent(tmp_path, monkeypatch):
    calls = []

    def post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return Response()

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    config = CostAlertConfig(webhook_url="https://example.test/hook?token=private")
    state_path = tmp_path / "alerts.json"
    manager = CostAlertManager(config, "run-1", state_path)

    assert manager.process(0.4999, 1.0) == []
    events = manager.process(0.5, 1.0, unknown_usage_results=2)
    assert [(event["threshold_percent"], event["status"]) for event in events] == [
        (50, "sent")
    ]
    assert calls[0][1]["unknown_usage_results"] == 2
    assert calls[0][1]["cost_basis"] == "known_pricing_usage"
    assert manager.process(0.95, 1.0) == [
        pytest.approx({
            "run_id": "run-1", "threshold_percent": 80, "channel": "webhook",
            "status": "sent", "accumulated_cost_usd": 0.95, "budget_cap_usd": 1.0,
            "unknown_usage_results": 0, "attempts": 1,
        }),
        pytest.approx({
            "run_id": "run-1", "threshold_percent": 90, "channel": "webhook",
            "status": "sent", "accumulated_cost_usd": 0.95, "budget_cap_usd": 1.0,
            "unknown_usage_results": 0, "attempts": 1,
        }),
    ]
    assert len(calls) == 3
    resumed = CostAlertManager(config, "run-1", state_path)
    assert resumed.process(1.25, 1.0) == []
    assert len(calls) == 3
    saved = json.loads(state_path.read_text())
    assert saved["delivered"] == {"50": ["webhook"], "80": ["webhook"], "90": ["webhook"]}
    assert "private" not in state_path.read_text()


def test_failed_channel_retries_once_per_manager_then_on_resume(tmp_path, monkeypatch):
    calls = []

    def post(url, *, json, timeout):
        calls.append(url)
        return Response(503 if len(calls) <= 3 else 200)

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    config = CostAlertConfig(
        thresholds=[50], webhook_url="https://example.test/hook?secret=private", max_retries=2
    )
    path = tmp_path / "alerts.json"
    first = CostAlertManager(config, "run-2", path)
    events = first.process(0.6, 1.0)
    assert len(calls) == 3
    assert events[0]["status"] == "failed"
    assert events[0]["error_type"] == "http_status_503"
    assert events[0]["attempts"] == 3
    assert first.process(0.9, 1.0) == []
    assert len(calls) == 3

    resumed = CostAlertManager(config, "run-2", path)
    retry = resumed.process(0.9, 1.0)
    assert retry[0]["status"] == "sent"
    assert retry[0]["attempts"] == 1
    assert len(calls) == 4
    assert CostAlertManager(config, "run-2", path).process(0.9, 1.0) == []
    assert "private" not in path.read_text()


@pytest.mark.parametrize(
    "status_code, expected_attempts",
    [(400, 1), (408, 1), (429, 3), (500, 3), (503, 3)],
)
def test_http_retries_only_rate_limit_and_server_errors(
    tmp_path, monkeypatch, status_code, expected_attempts
):
    calls = []

    def post(url, *, json, timeout):
        calls.append(url)
        return Response(status_code)

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    config = CostAlertConfig(
        thresholds=[50], webhook_url="https://example.test/private-hook", max_retries=2
    )
    path = tmp_path / f"{status_code}.json"
    event = CostAlertManager(config, f"http-{status_code}", path).process(0.5, 1.0)[0]
    assert event["status"] == "failed"
    assert event["attempts"] == expected_attempts
    assert event["error_type"] == f"http_status_{status_code}"
    assert len(calls) == expected_attempts
    assert "private-hook" not in path.read_text()


def test_smtp_retries_transient_replies_but_not_permanent_auth_failure(tmp_path, monkeypatch):
    calls = []
    status = 421

    class FailingSMTP:
        def __init__(self, host, port, timeout):
            calls.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self, *, context):
            pass

        def login(self, username, password):
            raise smtplib.SMTPAuthenticationError(status, b"private-password")

    monkeypatch.setattr("src.cost_alert.smtplib.SMTP", FailingSMTP)
    config = CostAlertConfig(
        thresholds=[50], smtp_host="smtp.example.test", smtp_username="user",
        smtp_password="private-password", smtp_from="from@example.test",
        smtp_to=["to@example.test"], max_retries=2,
    )
    transient_path = tmp_path / "transient.json"
    transient = CostAlertManager(config, "smtp-transient", transient_path).process(0.5, 1.0)[0]
    assert transient["attempts"] == 3
    assert transient["error_type"] == "smtp_error"
    assert len(calls) == 3

    status = 535
    permanent_path = tmp_path / "permanent.json"
    permanent = CostAlertManager(config, "smtp-permanent", permanent_path).process(0.5, 1.0)[0]
    assert permanent["attempts"] == 1
    assert permanent["error_type"] == "smtp_error"
    assert len(calls) == 4
    assert "private-password" not in permanent_path.read_text()


@pytest.mark.parametrize(
    "error, expected_attempts, error_type",
    [
        (requests.Timeout("secret URL"), 3, "network_error"),
        (requests.exceptions.ChunkedEncodingError("secret URL"), 3, "network_error"),
        (requests.exceptions.SSLError("secret URL"), 1, "network_error"),
        (requests.exceptions.InvalidURL("secret URL"), 1, "request_error"),
        (requests.HTTPError("secret URL"), 1, "http_error"),
    ],
)
def test_http_exception_retry_policy_and_redaction(
    tmp_path, monkeypatch, error, expected_attempts, error_type
):
    calls = []

    def post(url, *, json, timeout):
        calls.append(url)
        raise error

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    config = CostAlertConfig(
        thresholds=[50], webhook_url="https://example.test/private-hook", max_retries=2
    )
    state_path = tmp_path / "http-errors.json"
    event = CostAlertManager(config, "http-errors", state_path).process(0.5, 1.0)[0]
    assert event["attempts"] == expected_attempts
    assert event["error_type"] == error_type
    assert len(calls) == expected_attempts
    assert "secret" not in json.dumps(event).lower()
    assert "secret" not in state_path.read_text().lower()


@pytest.mark.parametrize(
    "error, expected_attempts",
    [
        (smtplib.SMTPServerDisconnected("secret"), 3),
        (smtplib.SMTPException("secret"), 1),
        (ssl.SSLError("secret"), 1),
        (OSError("secret"), 3),
    ],
)
def test_smtp_exception_retry_policy_and_redaction(
    tmp_path, monkeypatch, error, expected_attempts
):
    calls = []

    class FailingSMTP:
        def __init__(self, host, port, timeout):
            calls.append(host)
            raise error

    monkeypatch.setattr("src.cost_alert.smtplib.SMTP", FailingSMTP)
    config = CostAlertConfig(
        thresholds=[50], smtp_host="smtp.example.test", smtp_from="from@example.test",
        smtp_to=["to@example.test"], max_retries=2,
    )
    state_path = tmp_path / "smtp-errors.json"
    event = CostAlertManager(config, "smtp-errors", state_path).process(0.5, 1.0)[0]
    assert event["attempts"] == expected_attempts
    assert event["error_type"] == "smtp_error"
    assert len(calls) == expected_attempts
    assert "secret" not in json.dumps(event).lower()
    assert "secret" not in state_path.read_text().lower()


def test_channels_keep_independent_success_state_and_hide_errors(tmp_path, monkeypatch):
    secret_url = "https://example.test/path/secret-token"
    calls = []

    def post(url, *, json, timeout):
        calls.append(url)
        if url == secret_url and len([item for item in calls if item == secret_url]) == 1:
            raise requests.ConnectionError(f"Unable to connect to {secret_url}")
        return Response()

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    config = CostAlertConfig(
        thresholds=[50],
        slack_webhook_url="https://hooks.slack.test/private-token",
        webhook_url=secret_url,
        max_retries=0,
    )
    path = tmp_path / "alerts.json"
    events = CostAlertManager(config, "run-3", path).process(0.5, 1.0)
    assert [(event["channel"], event["status"]) for event in events] == [
        ("slack", "sent"), ("webhook", "failed")
    ]
    assert calls == ["https://hooks.slack.test/private-token", secret_url]
    assert secret_url not in json.dumps(events)
    assert secret_url not in path.read_text()
    assert "private-token" not in path.read_text()

    retry = CostAlertManager(config, "run-3", path).process(0.8, 1.0)
    assert [(event["channel"], event["status"]) for event in retry] == [
        ("webhook", "sent")
    ]
    assert calls.count("https://hooks.slack.test/private-token") == 1


def test_smtp_delivery_uses_timeout_tls_and_login(tmp_path, monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self, *, context):
            calls.append(("starttls", bool(context)))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message.get_content()))

    monkeypatch.setattr("src.cost_alert.smtplib.SMTP", FakeSMTP)
    config = CostAlertConfig(
        thresholds=[80], smtp_host="smtp.example.test", smtp_port=2525,
        smtp_username="user", smtp_password="private-password",
        smtp_from="sender@example.test", smtp_to=["recipient@example.test"],
        timeout_seconds=3,
    )
    path = tmp_path / "alerts.json"
    events = CostAlertManager(config, "run-4", path).process(0.8, 1.0, 1)
    assert events[0]["status"] == "sent"
    assert calls[0] == ("connect", "smtp.example.test", 2525, 3.0)
    assert calls[1] == ("starttls", True)
    assert calls[2] == ("login", "user", "private-password")
    assert "unknown usage: 1" in calls[3][2]
    assert "private-password" not in path.read_text()
    assert "private-password" not in json.dumps(events)


def test_local_alert_and_state_validation(tmp_path):
    path = tmp_path / "alerts.json"
    config = CostAlertConfig(thresholds=[50])
    manager = CostAlertManager(config, "run-5", path)
    assert manager.process(0.5, 1.0) == [
        {
            "run_id": "run-5", "threshold_percent": 50, "channel": "log",
            "status": "triggered", "accumulated_cost_usd": 0.5,
            "budget_cap_usd": 1.0, "unknown_usage_results": 0, "attempts": 0,
        }
    ]
    assert CostAlertManager(config, "run-5", path).process(0.6, 1.0) == []
    with pytest.raises(ValueError, match="another run"):
        CostAlertManager(config, "other-run", path)
    path.write_text("not JSON")
    with pytest.raises(ValueError, match="cannot be read safely"):
        CostAlertManager(config, "run-5", path)


def test_concurrent_calls_deliver_once(tmp_path, monkeypatch):
    calls = []

    def post(url, *, json, timeout):
        calls.append(url)
        return Response()

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    manager = CostAlertManager(
        CostAlertConfig(thresholds=[50], webhook_url="https://example.test/hook"),
        "run-6", tmp_path / "alerts.json",
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        events = list(pool.map(lambda _: manager.process(0.5, 1.0), range(20)))
    assert sum(map(len, events)) == 1
    assert calls == ["https://example.test/hook"]


@pytest.mark.parametrize(
    "accumulated, cap, unknown",
    [(float("nan"), 1, 0), (-0.1, 1, 0), (0.5, 0, 0), (0.5, 1, -1)],
)
def test_invalid_cost_input_rejected(tmp_path, accumulated, cap, unknown):
    manager = CostAlertManager(CostAlertConfig(), "run-7", tmp_path / "alerts.json")
    with pytest.raises(ValueError):
        manager.process(accumulated, cap, unknown)


@pytest.mark.parametrize(
    "overrides, expected_message",
    [
        ({"smtp_username": "user"}, "requires smtp_password"),
        ({"smtp_username": "user", "smtp_password": ""}, "requires smtp_password"),
        (
            {"smtp_username": "user", "smtp_password": "password", "smtp_use_starttls": False},
            "requires STARTTLS",
        ),
        ({"smtp_from": "sender@example.test\r\nBcc: victim@example.test"}, "line breaks"),
        ({"smtp_to": ["recipient@example.test\nBcc: victim@example.test"]}, "line breaks"),
    ],
)
def test_smtp_config_rejects_incomplete_auth_and_header_injection(overrides, expected_message):
    values = {
        "smtp_host": "smtp.example.test",
        "smtp_from": "sender@example.test",
        "smtp_to": ["recipient@example.test"],
    }
    with pytest.raises(ValueError, match=expected_message):
        CostAlertConfig(**{**values, **overrides})


@pytest.mark.parametrize("invalid_cap", [float("nan"), float("inf"), float("-inf")])
def test_harness_config_rejects_nonfinite_budget_cap(invalid_cap):
    with pytest.raises(ValueError):
        HarnessConfig(
            llm_config=LLMConfig(provider="local", api_key="", model="test-model"),
            dataset_path="unused.json",
            budget_cap_usd=invalid_cap,
        )


@pytest.mark.parametrize("run_id", ["run\rBcc: victim@example.test", "run\nheader", "run\x7f"])
def test_manager_rejects_control_characters_in_run_id(tmp_path, run_id):
    with pytest.raises(ValueError, match="Invalid run_id"):
        CostAlertManager(CostAlertConfig(), run_id, tmp_path / "alerts.json")
