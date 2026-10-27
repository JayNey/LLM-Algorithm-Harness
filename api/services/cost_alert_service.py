"""Best-effort Web alert delivery at committed evaluation cost boundaries."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import AlertEvent, AlertRule, Evaluation, EvaluationResult, utcnow
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
            endpoint = SecretStr(rule.target)
            if rule.channel == "slack":
                return CostAlertConfig(slack_webhook_url=endpoint)
            return CostAlertConfig(webhook_url=endpoint)
        if rule.channel == "smtp":
            return CostAlertConfig(**WebAlertSettings().model_dump(), smtp_to=[rule.target])
        return CostAlertConfig()

    def _claim(
        self, owner_id: str, rule: AlertRule, used: Decimal, cap: Decimal
    ) -> tuple[str, datetime] | None:
        # A unique primary key is an atomic claim on both SQLite and PostgreSQL.
        # Successful legacy rows also count, regardless of their random ID.
        event_id = str(
            uuid5(
                NAMESPACE_URL,
                f"cost-alert/{owner_id}/{rule.id}/{rule.threshold_pct}/{cap.normalize()}",
            )
        )
        now = utcnow()
        try:
            with self.sessions() as db, db.begin():
                existing = db.scalar(
                    select(AlertEvent)
                    .where(
                        AlertEvent.user_id == owner_id,
                        AlertEvent.rule_id == rule.id,
                        AlertEvent.threshold_pct == rule.threshold_pct,
                        AlertEvent.cap_usd == float(cap),
                    )
                    .limit(1)
                )
                if existing is not None:
                    if existing.channel != "pending" or existing.created_at > now - timedelta(
                        minutes=5
                    ):
                        return None
                    # Compare-and-delete prevents stealing a renewed lease.
                    removed = cast(
                        CursorResult[Any],
                        db.execute(
                            delete(AlertEvent).where(
                                AlertEvent.id == existing.id,
                                AlertEvent.channel == "pending",
                                AlertEvent.created_at == existing.created_at,
                            )
                        ),
                    )
                    if removed.rowcount != 1:
                        return None
                db.add(
                    AlertEvent(
                        id=event_id,
                        user_id=owner_id,
                        rule_id=rule.id,
                        threshold_pct=rule.threshold_pct,
                        used_usd=float(used),
                        cap_usd=float(cap),
                        channel="pending",
                        created_at=now,
                    )
                )
            return event_id, now
        except IntegrityError:
            # Another worker claimed the same crossing first (or rule deleted).
            return None

    def _finish(self, claim: tuple[str, datetime], channel: str, success: bool) -> None:
        event_id, claimed_at = claim
        with self.sessions() as db, db.begin():
            conditions = (
                AlertEvent.id == event_id,
                AlertEvent.channel == "pending",
                AlertEvent.created_at == claimed_at,
            )
            if success:
                db.execute(
                    update(AlertEvent)
                    .where(*conditions)
                    .values(channel=channel, created_at=utcnow())
                )
            else:
                db.execute(delete(AlertEvent).where(*conditions))

    def _process(self, owner_id: str) -> None:
        with self.sessions() as db:
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
            unknown_usage_results = (
                sum(
                    1
                    for metrics in db.scalars(
                        select(EvaluationResult.metrics)
                        .join(Evaluation, Evaluation.id == EvaluationResult.evaluation_id)
                        .where(Evaluation.user_id == owner_id)
                    )
                    if metrics and metrics.get("cost_unknown")
                )
                if rules
                else 0
            )
        # No database transaction remains open while contacting remote systems.
        for rule in rules:
            if used * 100 < cap * rule.threshold_pct:
                continue
            identity = (rule.id, rule.threshold_pct, float(cap))
            if identity in self._attempted:
                continue
            claim = self._claim(owner_id, rule, used, cap)
            if claim is None:
                continue
            self._attempted.add(identity)
            success = False
            try:
                sender = CostAlertSender(self._config(rule), self.run_id, follow_redirects=False)
                payload: dict[str, Any] = {
                    "event": "cost_alert",
                    "run_id": self.run_id,
                    "rule_id": rule.id,
                    "threshold_percent": rule.threshold_pct,
                    "accumulated_cost_usd": float(used),
                    "budget_cap_usd": float(cap),
                    "known_budget_percent": float(used * 100 / cap),
                    "unknown_usage_results": unknown_usage_results,
                    "cost_basis": "owner_known_pricing_usage",
                }
                success, attempts, error = sender.deliver(rule.channel, payload)
                if not success:
                    logger.warning(
                        "web_cost_alert_failed rule_id=%s attempts=%s error_type=%s",
                        rule.id,
                        attempts,
                        error,
                    )
            except Exception as exc:
                # Validation errors can contain endpoints or credentials.
                logger.warning(
                    "web_cost_alert_failed rule_id=%s error_type=%s", rule.id, type(exc).__name__
                )
            finally:
                self._finish(claim, rule.channel, success)
