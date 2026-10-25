"""Bounded, single-flight observations of the API's required databases."""

import threading
import time
from collections.abc import Callable
from typing import Any

READINESS_TIMEOUT_SECONDS = 1.0


class ReadinessCheck:
    """Keep at most one daemon probe alive, even when a driver never returns."""

    def __init__(
        self,
        probe: Callable[[], dict[str, Any]],
        *,
        timeout: float = READINESS_TIMEOUT_SECONDS,
        ttl: float = 1.0,
    ):
        self._probe = probe
        self._timeout, self._ttl = timeout, ttl
        self._condition = threading.Condition()
        self._running = False
        self._deadline = 0.0
        self._expires = 0.0
        self._ready = False

    def _collect(self) -> None:
        ready = False
        try:
            observation = self._probe()
            ready = (
                observation["status"] == "ok"
                and all(
                    observation[name]["status"] == "ok"
                    for name in ("authentication", "files", "business_database")
                )
                and observation["business_database"]["migration"]["status"] == "ok"
            )
        except Exception:
            # Driver errors and malformed evidence may contain private details.
            pass
        with self._condition:
            now = time.monotonic()
            self._ready = ready if now < self._deadline else False
            self._expires = now + self._ttl
            self._running = False
            self._condition.notify_all()

    def check(self, *, deadline: float | None = None) -> bool:
        with self._condition:
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                return False
            if now < self._expires:
                return self._ready
            if not self._running:
                self._running = True
                self._deadline = min(now + self._timeout, deadline or float("inf"))
                try:
                    threading.Thread(target=self._collect, daemon=True).start()
                except RuntimeError:
                    self._running = False
                    self._ready = False
                    self._expires = time.monotonic() + self._ttl
                    return False
            while self._running:
                remaining = min(self._deadline, deadline or float("inf")) - time.monotonic()
                if remaining <= 0:
                    self._ready = False
                    self._expires = time.monotonic() + self._ttl
                    return False
                self._condition.wait(remaining)
            return self._ready
