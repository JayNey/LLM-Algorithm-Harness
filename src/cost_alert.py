"""Durable, best-effort delivery of run-level cost threshold alerts.

The amount used for threshold decisions is the known-pricing cost supplied by
``RunCostMonitor``. Unknown-usage results are reported as a separate count;
they are never interpreted as free usage. Successful deliveries are persisted
per channel, while failed channels get one bounded retry cycle per manager
instance and can be retried when a run is resumed with a new instance.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import threading
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from src.models import CostAlertConfig

_STATE_VERSION = 1


def _amount(value: float | Decimal, name: str, *, positive: bool = False) -> Decimal:
    """Convert caller-supplied numeric values without float threshold drift."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be a finite {qualifier} number")
    return amount


class CostAlertManager:
    """Send each crossed threshold to configured channels at most once per run.

    ``state_path`` is a dedicated JSON file for this run, typically below the
    task output directory. The manager is safe for concurrent worker callbacks
    within one process. A new manager loads successful and failed channel state
    so only failed channels are retried on resume.
    """

    def __init__(self, config: CostAlertConfig, run_id: str, state_path: str | Path):
        if (
            not run_id
            or Path(run_id).name != run_id
            or "/" in run_id
            or "\\" in run_id
            or any(ord(char) < 32 or ord(char) == 127 for char in run_id)
        ):
            raise ValueError("Invalid run_id")
        self.config = config
        self.run_id = run_id
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._attempted: set[tuple[int, str]] = set()
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        try:
            with self.state_path.open("r", encoding="utf-8") as stream:
                state = json.load(stream)
        except FileNotFoundError:
            return {"version": _STATE_VERSION, "run_id": self.run_id, "delivered": {}, "failed": {}}
        except (OSError, ValueError) as exc:
            raise ValueError("Cost alert state cannot be read safely") from exc
        if (
            not isinstance(state, dict)
            or state.get("version") != _STATE_VERSION
            or state.get("run_id") != self.run_id
            or not isinstance(state.get("delivered"), dict)
            or not isinstance(state.get("failed"), dict)
        ):
            raise ValueError("Cost alert state is invalid or belongs to another run")
        for threshold, channels in state["delivered"].items():
            if not str(threshold).isdigit() or not isinstance(channels, list) or any(
                channel not in {"slack", "webhook", "smtp", "log"} for channel in channels
            ):
                raise ValueError("Cost alert state has invalid delivery entries")
        for threshold, channels in state["failed"].items():
            if not str(threshold).isdigit() or not isinstance(channels, dict) or any(
                channel not in {"slack", "webhook", "smtp"}
                or not isinstance(detail, dict)
                or type(detail.get("attempts")) is not int
                or detail["attempts"] < 1
                or detail.get("error_type") not in {
                    "http_error", "network_error", "request_error", "smtp_error", "delivery_error"
                }
                and not str(detail.get("error_type", "")).startswith("http_status_")
                for channel, detail in channels.items()
            ):
                raise ValueError("Cost alert state has invalid failure entries")
        return state

    def _save_state(self) -> None:
        """Replace JSON atomically after fsyncing a private temporary file."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(f".{self.state_path.name}.{uuid4().hex}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self._state, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.state_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _channels(self) -> list[str]:
        channels = []
        if self.config.slack_webhook_url is not None:
            channels.append("slack")
        if self.config.webhook_url is not None:
            channels.append("webhook")
        if self.config.smtp_host is not None:
            channels.append("smtp")
        return channels or ["log"]

    def _payload(
        self, threshold: int, accumulated: Decimal, cap: Decimal, unknown_usage_results: int
    ) -> dict[str, Any]:
        return {
            "event": "cost_alert",
            "run_id": self.run_id,
            "threshold_percent": threshold,
            "accumulated_cost_usd": float(accumulated),
            "budget_cap_usd": float(cap),
            "known_budget_percent": float(accumulated * 100 / cap),
            "unknown_usage_results": unknown_usage_results,
            "cost_basis": "known_pricing_usage",
        }

    def _send_webhook(self, channel: str, payload: dict[str, Any]) -> None:
        url_secret = (
            self.config.slack_webhook_url if channel == "slack" else self.config.webhook_url
        )
        assert url_secret is not None
        url = url_secret.get_secret_value()
        if channel == "slack":
            unknown = payload["unknown_usage_results"]
            note = f"; {unknown} result(s) have unknown usage" if unknown else ""
            body: dict[str, Any] = {
                "text": (
                    f"Cost alert for run {self.run_id}: known cost "
                    f"${payload['accumulated_cost_usd']:.4f} reached the "
                    f"{payload['threshold_percent']}% threshold of "
                    f"${payload['budget_cap_usd']:.4f}{note}."
                )
            }
        else:
            body = payload
        response = requests.post(url, json=body, timeout=self.config.timeout_seconds)
        response.raise_for_status()

    def _send_smtp(self, payload: dict[str, Any]) -> None:
        assert self.config.smtp_host is not None
        assert self.config.smtp_from is not None
        message = EmailMessage()
        message["From"] = self.config.smtp_from
        message["To"] = ", ".join(self.config.smtp_to)
        message["Subject"] = (
            f"Cost alert: run {self.run_id} reached {payload['threshold_percent']}%"
        )
        unknown = payload["unknown_usage_results"]
        message.set_content(
            f"Run: {self.run_id}\n"
            f"Known cost: ${payload['accumulated_cost_usd']:.4f}\n"
            f"Budget cap: ${payload['budget_cap_usd']:.4f}\n"
            f"Threshold: {payload['threshold_percent']}%\n"
            f"Results with unknown usage: {unknown}\n"
            "The known cost may be lower than actual spend when usage is unknown.\n"
        )
        with smtplib.SMTP(
            self.config.smtp_host,
            self.config.smtp_port,
            timeout=self.config.timeout_seconds,
        ) as smtp:
            if self.config.smtp_use_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self.config.smtp_username:
                password = (
                    self.config.smtp_password.get_secret_value()
                    if self.config.smtp_password is not None
                    else ""
                )
                smtp.login(self.config.smtp_username, password)
            smtp.send_message(message)

    def _deliver(self, channel: str, payload: dict[str, Any]) -> tuple[bool, int, str | None]:
        if channel == "log":
            return True, 0, None
        last_error: str | None = None
        for attempt in range(1, self.config.max_retries + 2):
            try:
                if channel in {"slack", "webhook"}:
                    self._send_webhook(channel, payload)
                else:
                    self._send_smtp(payload)
                return True, attempt, None
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                last_error = f"http_status_{status}" if status is not None else "http_error"
                if status != 429 and (status is None or not 500 <= status <= 599):
                    return False, attempt, last_error
            except requests.exceptions.SSLError:
                # A certificate/protocol failure needs a configuration fix.
                last_error = "network_error"
                return False, attempt, last_error
            except (
                requests.Timeout,
                requests.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
            ):
                last_error = "network_error"
            except requests.RequestException:
                last_error = "request_error"
                return False, attempt, last_error
            except smtplib.SMTPResponseException as exc:
                last_error = "smtp_error"
                if not 400 <= exc.smtp_code <= 499:
                    return False, attempt, last_error
            except smtplib.SMTPServerDisconnected:
                last_error = "smtp_error"
            except smtplib.SMTPException:
                last_error = "smtp_error"
                return False, attempt, last_error
            except ssl.SSLError:
                last_error = "smtp_error"
                return False, attempt, last_error
            except OSError:
                last_error = "smtp_error" if channel == "smtp" else "network_error"
            except Exception:
                # E.g. malformed SMTP headers; never surface an exception
                # message that may include an endpoint or credential.
                last_error = "delivery_error"
                return False, attempt, last_error
        return False, self.config.max_retries + 1, last_error

    def process(
        self,
        accumulated_cost_usd: float | Decimal,
        budget_cap_usd: float | Decimal | None,
        unknown_usage_results: int = 0,
    ) -> list[dict[str, Any]]:
        """Return safe events for newly crossed and delivered thresholds.

        A failed channel is attempted only once per manager instance, even if
        later units keep the known cost above the same threshold. Constructing
        a new manager for a resumed run permits another bounded retry cycle.
        """
        if budget_cap_usd is None:
            return []
        accumulated = _amount(accumulated_cost_usd, "accumulated_cost_usd")
        cap = _amount(budget_cap_usd, "budget_cap_usd", positive=True)
        if type(unknown_usage_results) is not int or unknown_usage_results < 0:
            raise ValueError("unknown_usage_results must be a non-negative integer")
        events: list[dict[str, Any]] = []
        with self._lock:
            for threshold in self.config.thresholds:
                if accumulated * 100 < cap * threshold:
                    continue
                key = str(threshold)
                delivered = self._state["delivered"].setdefault(key, [])
                for channel in self._channels():
                    identity = (threshold, channel)
                    if channel in delivered or identity in self._attempted:
                        continue
                    self._attempted.add(identity)
                    payload = self._payload(threshold, accumulated, cap, unknown_usage_results)
                    successful, attempts, error = self._deliver(channel, payload)
                    event = {
                        "run_id": self.run_id,
                        "threshold_percent": threshold,
                        "channel": channel,
                        "status": "triggered" if channel == "log" else "sent" if successful else "failed",
                        "accumulated_cost_usd": payload["accumulated_cost_usd"],
                        "budget_cap_usd": payload["budget_cap_usd"],
                        "unknown_usage_results": unknown_usage_results,
                        "attempts": attempts,
                    }
                    if successful:
                        delivered.append(channel)
                        self._state["failed"].get(key, {}).pop(channel, None)
                    else:
                        event["error_type"] = error or "delivery_error"
                        self._state["failed"].setdefault(key, {})[channel] = {
                            "attempts": attempts,
                            "error_type": event["error_type"],
                        }
                    self._save_state()
                    events.append(event)
        return events
