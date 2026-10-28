"""Persisted experiment/A-B spend, migration and conservative backfill (#307)."""

import json
from datetime import datetime

import pytest
from sqlalchemy import inspect, select, text

from api.db import downgrade, make_engine, make_session_factory, run_migrations, upgrade
from api.db.models import ABTest, Experiment
from src.models import LLMResponse, TokenUsage


def test_migration_preserves_legacy_jobs_as_unknown_and_roundtrips(tmp_path):
    url = f"sqlite:///{tmp_path}/migration.sqlite3"
    upgrade(url, "0004")
    engine = make_engine(url)
    with engine.begin() as db:
        for table in ("experiments", "ab_tests"):
            db.execute(
                text(
                    f"INSERT INTO {table} (id,user_id,name,status,config,created_at,updated_at) "
                    "VALUES ('old','alice','legacy','failed','{}', '2026-10-01','2026-10-01')"
                )
            )
    run_migrations(engine)
    assert "spend_records" in inspect(engine).get_table_names()
    with engine.connect() as db:
        assert db.execute(text("SELECT cost_tracking_complete FROM experiments")).scalar() == 0
        assert db.execute(text("SELECT cost_tracking_complete FROM ab_tests")).scalar() == 0
    downgrade(url, "0004")
    assert "spend_records" not in inspect(engine).get_table_names()
    run_migrations(engine)
    with make_session_factory(engine)() as db, db.begin():
        db.add(Experiment(id="new", user_id="alice", config={}))
    with make_session_factory(engine)() as db:
        assert db.get(Experiment, "new").cost_tracking_complete is True
        assert db.get(Experiment, "old").cost_tracking_complete is False
    engine.dispose()


def response(*, cost=0.3, missing=False, price_known=True):
    return LLMResponse(
        text="private provider output",
        model="gpt-4o-mini",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        usage_missing=missing,
        pricing_metadata={
            "total_cost": cost,
            "usage_known": not missing,
            "pricing_known": price_known,
            "source": "override" if price_known else "unknown",
            "prompt_price_per_1k": 1,
            "completion_price_per_1k": 4,
        },
    )


@pytest.fixture
def store(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/spend.sqlite3")
    run_migrations(engine)
    factory = make_session_factory(engine)
    with factory() as db, db.begin():
        db.add(Experiment(id="experiment", user_id="alice", config={}))
        db.add(ABTest(id="ab", user_id="alice", config={}))
    yield factory
    engine.dispose()


def test_recorder_replay_is_idempotent_and_snapshots_contain_no_content(store):
    from api.db.models import SpendRecord
    from api.services.spend_records import SpendRecorder

    recorder = SpendRecorder(store, "experiments", "experiment", "alice")
    record = recorder.callback(
        model="requested", strategy="vanilla", problem_id="p1", difficulty="easy"
    )
    for _ in range(2):
        record("same-call", response(), False)
    with store() as db:
        rows = db.scalars(select(SpendRecord)).all()
        assert len(rows) == 1
        assert rows[0].cost_usd == pytest.approx(0.3)
        assert rows[0].model == "gpt-4o-mini"
        assert rows[0].difficulty == "easy"
        assert rows[0].usage["prompt_tokens"] == 100
        assert rows[0].pricing["source"] == "override"
        assert "private provider output" not in json.dumps(rows[0].pricing)


@pytest.mark.parametrize(
    "reply,cached,want,reason",
    [
        (response(missing=True), False, None, "missing_usage"),
        (response(cost=None, price_known=False), False, None, "missing_pricing"),
        (None, False, None, "missing_response"),
        (response(missing=True), True, 0, None),
    ],
)
def test_unknown_is_not_free_but_cache_has_zero_increment(store, reply, cached, want, reason):
    from api.db.models import SpendRecord
    from api.services.spend_records import SpendRecorder

    SpendRecorder(store, "ab_tests", "ab", "alice").callback(model="demo", strategy="vanilla")(
        "call", reply, cached
    )
    with store() as db:
        row = db.get(SpendRecord, "call")
        assert row.cost_usd == want
        assert row.unknown_reason == reason
        assert row.cached is cached


def test_recorder_rejects_other_owners_and_unsupported_sources(store):
    from api.services.spend_records import SpendRecorder

    with pytest.raises(ValueError):
        SpendRecorder(store, "evaluations", "experiment", "alice")
    with pytest.raises(ValueError):
        SpendRecorder(store, "experiments", "experiment", "bob").callback(
            model="demo", strategy="vanilla"
        )("stolen", response(), False)


def test_backfill_only_explicit_snapshots_and_repeated_runs_do_not_double_count(store, tmp_path):
    from api.db.models import SpendRecord
    from api.services.spend_records import backfill_spend

    output = tmp_path / "legacy"
    combo = output / "combo"
    combo.mkdir(parents=True)
    (output / "experiment.json").write_text(
        json.dumps(
            {
                "combinations": [
                    {
                        "combo_id": "combo",
                        "combo_dir": "combo",
                        "model": "demo",
                        "strategy": "vanilla",
                        "repeat": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (combo / "summary.json").write_text(
        json.dumps(
            {
                "vanilla": {
                    "pricing_metadata": {
                        "total_cost": 0.4,
                        "has_actual_pricing": True,
                        "unknown_usage": False,
                        "unknown_pricing": False,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with store() as db, db.begin():
        row = db.get(Experiment, "experiment")
        row.cost_tracking_complete = False
        row.output_dir = str(output)
        row.completed_at = datetime(2026, 10, 1, 10)
        row.status = "completed"
        ab = db.get(ABTest, "ab")
        ab.cost_tracking_complete = False
        ab.output_dir = str(output)
        ab.status = "completed"
    assert backfill_spend(store, dry_run=True)["inserted"] == 1
    with store() as db:
        assert db.scalars(select(SpendRecord)).all() == []
    assert backfill_spend(store)["inserted"] == 1
    assert backfill_spend(store)["inserted"] == 0
    with store() as db:
        rows = db.scalars(select(SpendRecord)).all()
        assert len(rows) == 1
        assert rows[0].cost_usd == 0.4
        assert rows[0].occurred_at == datetime(2026, 10, 1, 10)
        assert rows[0].pricing["timestamp_basis"] == "legacy_completed_at"
        assert db.get(Experiment, "experiment").cost_tracking_complete is False


def test_concurrent_replays_commit_one_consumption(store):
    from concurrent.futures import ThreadPoolExecutor

    from api.db.models import SpendRecord
    from api.services.spend_records import SpendRecorder

    record = SpendRecorder(store, "experiments", "experiment", "alice").callback(
        model="demo", strategy="vanilla"
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: record("shared-event", response(), False), range(8)))
    with store() as db:
        assert len(db.scalars(select(SpendRecord)).all()) == 1
        assert db.get(SpendRecord, "shared-event").cost_usd == 0.3


@pytest.mark.parametrize("metadata", [[], {"combinations": [None]}, {"combinations": []}])
def test_backfill_reports_malformed_or_evidence_free_artifacts(store, tmp_path, metadata):
    from api.services.spend_records import backfill_spend

    output = tmp_path / "invalid"
    output.mkdir()
    (output / "experiment.json").write_text(json.dumps(metadata), encoding="utf-8")
    with store() as db, db.begin():
        row = db.get(Experiment, "experiment")
        row.cost_tracking_complete = False
        row.output_dir = str(output)
        row.status = "completed"
    result = backfill_spend(store)
    assert result["inserted"] == 0
    assert "experiment" in result["skipped"]


@pytest.mark.parametrize("summary", [{"vanilla": []}, {"vanilla": {"pricing_metadata": [1]}}])
def test_backfill_skips_malformed_nested_evidence(store, tmp_path, summary):
    from api.services.spend_records import backfill_spend

    output = tmp_path / "malformed"
    (output / "combo").mkdir(parents=True)
    (output / "experiment.json").write_text(
        json.dumps(
            {
                "combinations": [
                    {
                        "combo_id": "combo",
                        "combo_dir": "combo",
                        "model": "demo",
                        "strategy": "vanilla",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / "combo/summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with store() as db, db.begin():
        job = db.get(Experiment, "experiment")
        job.cost_tracking_complete = False
        job.output_dir = str(output)
    result = backfill_spend(store)
    assert result["inserted"] == 0
    assert result["skipped"]["experiment"] == "unverifiable_artifacts"
