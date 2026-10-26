"""Best-effort Web alert delivery at committed evaluation cost boundaries."""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.db.models import AlertEvent, AlertRule, Budget
from api.services.cost_service import CostService
from src.cost_alert import CostAlertSender
from src.models import CostAlertConfig

logger = logging.getLogger(__name__)


class WebAlertSettings(BaseSettings):
    """Worker SMTP connection; each rule supplies its own recipient."""

    model_config = SettingsConfigDict(env_prefix="COST_ALERT_", env_file=".env", extra="ignore")
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_use_starttls: bool = True


class WebCostAlertDispatcher:
    """Deduplicate successful rules across workers, retry failures on resume."""

    def __init__(self, sessions: Callable[[], Session], run_id: str):
        self.sessions = sessions
        self.run_id = run_id
        self._attempted: set[tuple[str, int, float]] = set()

    def process(self, owner_id: str) -> None:
        """Never let notification or history failures interrupt evaluation."""
        try:
            self._process(owner_id)
        except Exception as exc:
            logger.warning("web_cost_alert_processing_failed error_type=%s", type(exc).__name__)

    @staticmethod
    def _config(rule: AlertRule) -> CostAlertConfig:
        if rule.channel in {"slack", "webhook"}:
            key = "slack_webhook_url" if rule.channel == "slack" else "webhook_url"
            return CostAlertConfig(**{key: rule.target})
        if rule.channel == "smtp":
            return CostAlertConfig(**WebAlertSettings().model_dump(), smtp_to=[rule.target])
        return CostAlertConfig()

    def _process(self, owner_id: str) -> None:
        # A no-op UPDATE acquires a per-owner write lock before reading history:
        # row lock on PostgreSQL, write transaction on SQLite. Use a dedicated
        # session so commit/rollback cannot alter the worker's unit transaction.
        with self.sessions() as db, db.begin():
            db.execute(
                update(Budget)
                .where(Budget.user_id == owner_id)
                .values(updated_at=Budget.updated_at)
            )
            budget = CostService.execution_budget(db, owner_id)
            if budget is None or not budget["global_cap_usd"]:
                return
            cap = Decimal(str(budget["global_cap_usd"]))
            used = Decimal(str(budget["used_usd"]))
            rules = db.scalars(
                select(AlertRule)
                .where(AlertRule.user_id == owner_id, AlertRule.enabled.is_(True))
                .order_by(AlertRule.threshold_pct, AlertRule.id)
            ).all()
            for rule in rules:
                if used * 100 < cap * rule.threshold_pct:
                    continue
                identity = (rule.id, rule.threshold_pct, float(cap))
                if identity in self._attempted:
                    continue
                delivered = db.scalar(
                    select(AlertEvent.id)
                    .where(
                        AlertEvent.user_id == owner_id,
                        AlertEvent.rule_id == rule.id,
                        AlertEvent.threshold_pct == rule.threshold_pct,
                        AlertEvent.cap_usd == float(cap),
                    )
                    .limit(1)
                )
                if delivered:
                    continue
                self._attempted.add(identity)
                try:
                    sender = CostAlertSender(self._config(rule), self.run_id)
                    payload: dict[str, Any] = {
                        "event": "cost_alert",
                        "run_id": self.run_id,
                        "rule_id": rule.id,
                        "threshold_percent": rule.threshold_pct,
                        "accumulated_cost_usd": float(used),
                        "budget_cap_usd": float(cap),
                        "known_budget_percent": float(used * 100 / cap),
                        "unknown_usage_results": 0,
                        "cost_basis": "owner_known_pricing_usage",
                    }
                    success, attempts, error = sender.deliver(rule.channel, payload)
                except Exception as exc:
                    # Configuration errors can contain secrets in validation text.
                    logger.warning(
                        "web_cost_alert_failed rule_id=%s error_type=%s",
                        rule.id,
                        type(exc).__name__,
                    )
                    continue
                if not success:
                    logger.warning(
                        "web_cost_alert_failed rule_id=%s attempts=%s error_type=%s",
                        rule.id,
                        attempts,
                        error,
                    )
                    continue
                db.add(
                    AlertEvent(
                        id=str(uuid4()),
                        user_id=owner_id,
                        rule_id=rule.id,
                        threshold_pct=rule.threshold_pct,
                        used_usd=float(used),
                        cap_usd=float(cap),
                        channel=rule.channel,
                    )
                )
