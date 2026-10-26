"""Web notifications use committed owner spend and durable successful history."""

from unittest.mock import Mock

import pytest
import requests

from api.db import make_engine, make_session_factory, run_migrations
from api.db.models import AlertEvent, AlertRule, Budget, Evaluation


@pytest.fixture
def sessions(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    run_migrations(engine)
    factory = make_session_factory(engine)
    with factory() as db, db.begin():
        db.add(Budget(id="b", user_id="alice", global_cap_usd=1, action="pause"))
        db.add(
            Evaluation(
                id="e",
                user_id="alice",
                strategy_names=["vanilla"],
                problem_ids=["p"],
                problem_count=1,
                spent_usd=1,
            )
        )
    yield factory
    engine.dispose()


def add_rule(sessions, rule_id="rule", **values):
    with sessions() as db, db.begin():
        db.add(
            AlertRule(
                id=rule_id,
                user_id=values.pop("user_id", "alice"),
                threshold_pct=values.pop("threshold_pct", 100),
                channel=values.pop("channel", "webhook"),
                target=values.pop("target", "https://example.org/secret"),
                **values,
            )
        )


def dispatcher(sessions):
    from api.services.cost_alert_service import WebCostAlertDispatcher

    return WebCostAlertDispatcher(sessions, "e")


def test_delivers_100_percent_and_deduplicates_across_resume(sessions, monkeypatch):
    add_rule(sessions)
    sent = []

    def post(url, **kwargs):
        sent.append((url, kwargs))
        return Mock(raise_for_status=lambda: None)

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    dispatcher(sessions).process("alice")
    dispatcher(sessions).process("alice")
    assert len(sent) == 1
    assert sent[0][1]["json"]["threshold_percent"] == 100
    assert sent[0][1]["json"]["accumulated_cost_usd"] == 1
    assert sent[0][1]["timeout"] == 5
    with sessions() as db:
        events = db.query(AlertEvent).all()
        assert [(e.user_id, e.rule_id, e.used_usd) for e in events] == [("alice", "rule", 1)]


def test_disabled_foreign_below_threshold_and_no_cap_are_ignored(sessions, monkeypatch):
    add_rule(sessions, enabled=False)
    add_rule(sessions, "foreign", user_id="bob")
    add_rule(sessions, "below", threshold_pct=80)
    with sessions() as db, db.begin():
        db.get(Evaluation, "e").spent_usd = 0.79

    def forbidden(*args, **kwargs):
        pytest.fail("ineligible rule must not send")

    monkeypatch.setattr("src.cost_alert.requests.post", forbidden)
    dispatcher(sessions).process("alice")
    with sessions() as db, db.begin():
        db.get(Budget, "b").global_cap_usd = None
    dispatcher(sessions).process("alice")
    dispatcher(sessions).process("bob")
    with sessions() as db:
        assert db.query(AlertEvent).count() == 0


def test_failed_delivery_is_bounded_safe_and_resume_retries(sessions, monkeypatch, caplog):
    add_rule(sessions)
    add_rule(sessions, "log", channel="log", target="")
    attempts = []

    def fail(*args, **kwargs):
        attempts.append(1)
        raise requests.Timeout("secret-credential https://example.org/secret")

    monkeypatch.setattr("src.cost_alert.requests.post", fail)
    worker = dispatcher(sessions)
    worker.process("alice")
    worker.process("alice")
    assert len(attempts) == 3
    assert "secret-credential" not in caplog.text
    with sessions() as db:
        assert [r.rule_id for r in db.query(AlertEvent).all()] == ["log"]
    monkeypatch.setattr(
        "src.cost_alert.requests.post", lambda *a, **k: Mock(raise_for_status=lambda: None)
    )
    dispatcher(sessions).process("alice")
    with sessions() as db:
        assert db.query(AlertEvent).count() == 2


@pytest.mark.parametrize("channel", ["slack", "smtp"])
def test_slack_and_email_use_rule_target(sessions, monkeypatch, channel):
    target = "owner@example.org" if channel == "smtp" else "https://hooks.slack.com/services/secret"
    add_rule(sessions, channel=channel, target=target)
    sent = []
    if channel == "smtp":
        monkeypatch.setenv("COST_ALERT_SMTP_HOST", "smtp.example.org")
        monkeypatch.setenv("COST_ALERT_SMTP_FROM", "sender@example.org")
        smtp = Mock()
        smtp.__enter__ = lambda self: self
        smtp.__exit__ = lambda *args: None
        smtp.send_message.side_effect = sent.append
        monkeypatch.setattr("src.cost_alert.smtplib.SMTP", lambda *a, **k: smtp)
    else:

        def post(url, **kwargs):
            sent.append((url, kwargs["json"]))
            return Mock(raise_for_status=lambda: None)

        monkeypatch.setattr("src.cost_alert.requests.post", post)
    dispatcher(sessions).process("alice")
    assert len(sent) == 1
    if channel == "smtp":
        assert sent[0]["To"] == target
        assert "100%" in sent[0]["Subject"]
    else:
        assert sent[0][0] == target
        assert "100%" in sent[0][1]["text"]
    with sessions() as db:
        assert db.query(AlertEvent).one().channel == channel


def test_concurrent_workers_send_once(sessions, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    add_rule(sessions)
    sent = []

    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        return Mock(raise_for_status=lambda: None)

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: dispatcher(sessions).process("alice"), range(2)))
    assert len(sent) == 1
    with sessions() as db:
        assert db.query(AlertEvent).count() == 1


def test_unknown_usage_is_reported_without_inventing_spend(sessions, monkeypatch):
    from api.db.models import EvaluationResult

    add_rule(sessions)
    with sessions() as db, db.begin():
        db.add(
            EvaluationResult(
                id="result",
                evaluation_id="e",
                problem_id="p",
                strategy_name="vanilla",
                status="success",
                metrics={"cost_unknown": True, "cost_usd": 0},
            )
        )
    sent = []

    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        return Mock(raise_for_status=lambda: None)

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    dispatcher(sessions).process("alice")
    assert sent[0]["unknown_usage_results"] == 1
    assert sent[0]["accumulated_cost_usd"] == 1


def test_new_budget_cap_rearms_and_disabled_rule_is_reloaded(sessions, monkeypatch):
    add_rule(sessions)
    sent = []

    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        return Mock(raise_for_status=lambda: None)

    monkeypatch.setattr("src.cost_alert.requests.post", post)
    worker = dispatcher(sessions)
    worker.process("alice")
    with sessions() as db, db.begin():
        db.get(Budget, "b").global_cap_usd = 0.5
        db.get(AlertRule, "rule").enabled = False
    worker.process("alice")
    assert len(sent) == 1
    with sessions() as db, db.begin():
        db.get(AlertRule, "rule").enabled = True
    worker.process("alice")
    assert [p["budget_cap_usd"] for p in sent] == [1, 0.5]
