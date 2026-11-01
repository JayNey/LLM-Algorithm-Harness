"""Persisted per-user notifications for committed task and budget events."""

from __future__ import annotations

import base64
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db import (
    ABTest,
    BenchmarkSuite,
    Evaluation,
    Experiment,
    InAppNotification,
    make_engine,
    make_session_factory,
    run_migrations,
)
from api.db.engine import business_database_url
from api.db.models import utcnow

RETENTION = timedelta(days=90)
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
KINDS = frozenset({"task_completed", "budget_alert", "system"})
TASK_KINDS = frozenset({"evaluation", "experiment", "benchmark", "ab_test"})
SAFE_PARAM_KEYS = frozenset(
    {
        "entity_id",
        "completed_count",
        "failed_count",
        "total_count",
        "threshold_pct",
        "used_usd",
        "cap_usd",
    }
)
_SECRET = re.compile(r"(sk-|bearer|api[_-]?key|secret|password|smtp|https?://)", re.I)


def task_event_key(kind: str, entity_id: str) -> str:
    if kind not in TASK_KINDS:
        raise ValueError(f"unsupported task kind: {kind}")
    return f"task-completed/{kind}/{entity_id}"


def budget_event_key(rule_id: str, threshold_pct: int, cap: Decimal | float | str) -> str:
    return f"budget-alert/{rule_id}/{int(threshold_pct)}/{_cap_text(cap)}"


def sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Keep identifiers and amounts. Drop secrets, targets and raw errors."""

    clean: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if key not in SAFE_PARAM_KEYS or isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str) and 0 < len(value) <= 64 and _SECRET.search(value) is None:
            clean[key] = value
    return clean


class NotificationNotFound(LookupError):
    """The notification is not visible to this user."""


class NotificationService:
    """List and update one user's notifications. Event rows are never deleted."""

    def __init__(self, database_url: str | None = None):
        self._engine = make_engine(database_url or business_database_url())
        run_migrations(self._engine)
        self._sessions = make_session_factory(self._engine)

    def stage(
        self,
        session: Session,
        *,
        user_id: str,
        kind: str,
        event_key: str,
        title_key: str,
        body_key: str,
        params: dict[str, Any] | None = None,
        resource_kind: str | None = None,
        resource_id: str | None = None,
        href: str | None = None,
        created_at: datetime | None = None,
    ) -> InAppNotification:
        """Insert inside the caller's transaction. An existing event is left unchanged."""

        if kind not in KINDS:
            raise ValueError(f"unsupported notification kind: {kind}")
        existing = self._by_event(session, user_id, event_key)
        if existing is not None:
            return existing
        row = InAppNotification(
            id=str(uuid4()),
            user_id=user_id,
            kind=kind,
            event_key=event_key,
            title_key=title_key,
            body_key=body_key,
            params=sanitize_params(params),
            created_at=_naive(created_at) if created_at is not None else utcnow(),
            resource_kind=resource_kind,
            resource_id=resource_id,
            href=href,
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError:
            raced = self._by_event(session, user_id, event_key)
            if raced is None:
                raise
            return raced
        return row

    def list_notifications(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
        kind: str | None = None,
        unread: bool | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if kind is not None and kind not in KINDS:
            raise ValueError(f"unsupported notification kind: {kind}")
        page_size = min(max(limit, 1), MAX_LIMIT)
        moment = _naive(now) if now else utcnow()
        with self._sessions() as db:
            stmt = self._visible(user_id, moment)
            if kind is not None:
                stmt = stmt.where(InAppNotification.kind == kind)
            if unread is True:
                stmt = stmt.where(InAppNotification.read_at.is_(None))
            elif unread is False:
                stmt = stmt.where(InAppNotification.read_at.is_not(None))
            if cursor:
                stamp, note_id = _decode_cursor(cursor)
                stmt = stmt.where(
                    or_(
                        InAppNotification.created_at < stamp,
                        and_(
                            InAppNotification.created_at == stamp,
                            InAppNotification.id < note_id,
                        ),
                    )
                )
            rows = list(
                db.scalars(
                    stmt.order_by(
                        InAppNotification.created_at.desc(), InAppNotification.id.desc()
                    ).limit(page_size + 1)
                )
            )
            extra = len(rows) > page_size
            visible = rows[:page_size]
            return {
                "items": [self._view(db, user_id, row) for row in visible],
                "next_cursor": _encode_cursor(visible[-1]) if extra and visible else None,
                "unread_count": self._count_unread(db, user_id, moment),
                "server_time": _iso(moment),
            }

    def unread_count(self, user_id: str, *, now: datetime | None = None) -> int:
        moment = _naive(now) if now else utcnow()
        with self._sessions() as db:
            return self._count_unread(db, user_id, moment)

    def mark_read(
        self, user_id: str, note_id: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        moment = _naive(now) if now else utcnow()
        with self._sessions() as db, db.begin():
            row = self._owned_visible(db, user_id, note_id, moment)
            if row.read_at is None:
                row.read_at = moment
            return self._view(db, user_id, row)

    def mark_all_read(
        self, user_id: str, before: datetime | None = None, *, now: datetime | None = None
    ) -> dict[str, Any]:
        return self._batch(user_id, before, now=now, clear=False)

    def clear(
        self, user_id: str, before: datetime | None = None, *, now: datetime | None = None
    ) -> dict[str, Any]:
        return self._batch(user_id, before, now=now, clear=True)

    def _batch(
        self,
        user_id: str,
        before: datetime | None,
        *,
        now: datetime | None,
        clear: bool,
    ) -> dict[str, Any]:
        moment = _naive(now) if now else utcnow()
        cutoff = moment if before is None else min(_naive(before), moment)
        floor = moment - RETENTION
        with self._sessions() as db, db.begin():
            conditions = (
                InAppNotification.user_id == user_id,
                InAppNotification.cleared_at.is_(None),
                InAppNotification.created_at <= cutoff,
                InAppNotification.created_at >= floor,
            )
            if clear:
                values = {"cleared_at": moment}
            else:
                conditions = (*conditions, InAppNotification.read_at.is_(None))
                values = {"read_at": moment}
            result = db.execute(update(InAppNotification).where(*conditions).values(**values))
            updated = int(result.rowcount or 0)
            unread = self._count_unread(db, user_id, moment)
        return {"updated": updated, "cutoff": _iso(cutoff), "unread_count": unread}

    def _visible(self, user_id: str, moment: datetime):
        return select(InAppNotification).where(
            InAppNotification.user_id == user_id,
            InAppNotification.cleared_at.is_(None),
            InAppNotification.created_at >= moment - RETENTION,
        )

    def _count_unread(self, db: Session, user_id: str, moment: datetime) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(InAppNotification)
                .where(
                    InAppNotification.user_id == user_id,
                    InAppNotification.cleared_at.is_(None),
                    InAppNotification.read_at.is_(None),
                    InAppNotification.created_at >= moment - RETENTION,
                )
            )
            or 0
        )

    def _owned_visible(
        self, db: Session, user_id: str, note_id: str, moment: datetime
    ) -> InAppNotification:
        row = db.scalar(self._visible(user_id, moment).where(InAppNotification.id == note_id))
        if row is None:
            raise NotificationNotFound(note_id)
        return row

    @staticmethod
    def _by_event(session: Session, user_id: str, event_key: str) -> InAppNotification | None:
        return session.scalar(
            select(InAppNotification)
            .where(
                InAppNotification.user_id == user_id,
                InAppNotification.event_key == event_key,
            )
            .limit(1)
        )

    def _view(self, db: Session, user_id: str, row: InAppNotification) -> dict[str, Any]:
        available, href = _resource(db, user_id, row)
        return {
            "id": row.id,
            "kind": row.kind,
            "title_key": row.title_key,
            "body_key": row.body_key,
            "params": sanitize_params(row.params),
            "created_at": _iso(row.created_at),
            "read": row.read_at is not None,
            "href": href if available else None,
            "resource_available": available,
            "unavailable_reason": None if available else "resource_unavailable",
        }


def _resource(db: Session, user_id: str, row: InAppNotification) -> tuple[bool, str | None]:
    if row.resource_kind == "budget":
        return True, row.href or "/settings/budgets"
    model = {
        "evaluation": Evaluation,
        "experiment": Experiment,
        "benchmark": BenchmarkSuite,
        "ab_test": ABTest,
    }.get(row.resource_kind or "")
    if model is None or not row.resource_id:
        return False, None
    owned = db.get(model, row.resource_id)
    if owned is None or owned.user_id != user_id:
        return False, None
    return True, row.href


def _cap_text(cap: Decimal | float | str) -> str:
    text = format(Decimal(str(cap)).normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return _naive(value).isoformat(timespec="seconds")


def _encode_cursor(row: InAppNotification) -> str:
    raw = f"{_iso(row.created_at)}|{row.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        stamp, note_id = base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
        return datetime.fromisoformat(stamp), note_id
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid cursor") from exc
