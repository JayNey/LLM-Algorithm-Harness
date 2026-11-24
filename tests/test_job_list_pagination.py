"""List SQL must bound entity loads and keep frozen problem payloads in the DB (#515)."""

from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql

from api.datasets import public_dataset_config_sql
from api.db.models import ABTest, AsyncTask, Evaluation, Experiment
from api.services.ab_test_service import ABTestService
from api.services.evaluation_service import EvaluationService
from api.services.experiment_service import ExperimentService

CASES = [
    (EvaluationService, Evaluation, "list_evaluations"),
    (ExperimentService, Experiment, "list_experiments"),
    (ABTestService, ABTest, "list_tests"),
]
CREATED = datetime(2026, 11, 24)


@pytest.fixture(params=CASES, ids=["evaluations", "experiments", "ab-tests"])
def listing(request, tmp_path):
    service_type, model, method = request.param
    kwargs = {} if model is Evaluation else {"recover": False}
    service = service_type(f"sqlite:///{tmp_path}/business.db", **kwargs)
    try:
        yield service, model, getattr(service, method)
    finally:
        service._engine.dispose()


def seed(service, model, count):
    with service._session() as session, session.begin():
        for index in range(count + 5):
            values = {
                "id": f"job-{index:04d}",
                "user_id": "owner" if index < count else "other",
                "status": "completed" if index % 3 == 0 else "pending",
                "created_at": CREATED,
                "updated_at": CREATED,
            }
            if model is Evaluation:
                values.update(strategy_names=["vanilla"], problem_ids=["private-problem"])
            else:
                values["config"] = {
                    "dataset_path": "legacy.json",
                    "extra_public_field": {"keep": True},
                    "dataset_snapshot": {
                        "schema_version": 1,
                        "owner_id": "owner",
                        "problem_count": 1,
                        "sha256": "original-digest",
                        "problems": [{"id": "private-problem", "description": "x" * 10000}],
                    },
                }
            session.add(model(**values))


@contextmanager
def observe(service, model):
    statements, loaded = [], []

    def sql(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(statement.lower().split()))

    def load(instance, _context):
        loaded.append(dict(instance.__dict__))

    event.listen(service._engine, "before_cursor_execute", sql)
    event.listen(model, "load", load)
    try:
        yield statements, loaded
    finally:
        event.remove(model, "load", load)
        event.remove(service._engine, "before_cursor_execute", sql)


def item_id(item):
    return item.evaluation_id if hasattr(item, "evaluation_id") else item["id"]


@pytest.mark.parametrize("history", [200, 400])
def test_page_entity_loads_stay_bounded_as_history_grows(listing, history):
    service, model, list_page = listing
    seed(service, model, history)
    with observe(service, model) as (statements, loaded):
        items, total = list_page("owner", limit=20, offset=20)

    assert total == history
    assert [item_id(item) for item in items] == [f"job-{i:04d}" for i in range(20, 40)]
    assert len(loaded) == 20
    business_queries = [sql for sql in statements if f"from {model.__tablename__}" in sql]
    assert len(business_queries) == 2  # one count and one page, with no deferred fetches
    assert any("count(" in sql for sql in business_queries)
    page_sql = next(sql for sql in business_queries if "count(" not in sql)
    assert "limit" in page_sql and "offset" in page_sql
    assert f"order by {model.__tablename__}.created_at, {model.__tablename__}.id" in page_sql


@pytest.mark.parametrize(
    ("owner", "status", "offset"),
    [
        ("owner", "completed", 20),
        ("owner", "completed", 999),
        ("owner", "failed", 0),
        ("absent", None, 0),
    ],
)
def test_count_and_pages_share_owner_and_status_filters(listing, owner, status, offset):
    service, model, list_page = listing
    seed(service, model, 200)
    matches = [i for i in range(200) if status is None or (status == "completed" and i % 3 == 0)]
    if owner != "owner":
        matches = []
    with observe(service, model) as (statements, loaded):
        items, total = list_page(owner, status=status, limit=20, offset=offset)

    expected_ids = [f"job-{i:04d}" for i in matches[offset : offset + 20]]
    assert total == len(matches)
    assert [item_id(item) for item in items] == expected_ids
    assert [row["id"] for row in loaded] == expected_ids
    if not items:
        assert len(statements) == 2  # no task or result lookups for an empty page


def test_evaluation_page_omits_execution_only_problem_ids(listing):
    service, model, list_page = listing
    if model is not Evaluation:
        pytest.skip("Evaluation-specific field projection")
    seed(service, model, 200)
    with observe(service, model) as (statements, loaded):
        items, _ = list_page("owner")
    assert len(items) == 20
    assert all("problem_ids" not in row for row in loaded)
    assert all("evaluations.problem_ids" not in sql for sql in statements)


def test_job_page_receives_only_public_config_and_preserves_snapshot(listing):
    service, model, list_page = listing
    if model is Evaluation:
        pytest.skip("Experiment and A/B configuration projection")
    seed(service, model, 200)
    with service._session() as session:
        original = session.scalar(select(model.config).where(model.id == "job-0000"))
    with observe(service, model) as (_statements, loaded):
        items, _ = list_page("owner")

    public = {
        "dataset_path": "legacy.json",
        "extra_public_field": {"keep": True},
        "dataset_snapshot": {
            "schema_version": 1,
            "problem_count": 1,
            "sha256": "original-digest",
        },
    }
    assert items[0]["config"] == public
    assert loaded[0]["config"] == public  # projected by SQL, before response conversion
    with service._session() as session:
        assert session.scalar(select(model.config).where(model.id == "job-0000")) == original


@pytest.mark.parametrize("config", [{"dataset_path": "old.json"}, {"dataset_snapshot": None}])
def test_job_page_preserves_legacy_and_null_snapshot_config(listing, config):
    service, model, list_page = listing
    if model is Evaluation:
        pytest.skip("Experiment and A/B configuration projection")
    with service._session() as session, session.begin():
        session.add(model(id="legacy", user_id="owner", config=config))
    with observe(service, model) as (statements, loaded):
        items, total = list_page("owner")
    assert total == 1
    assert items[0]["config"] == config
    assert loaded[0]["config"] == config
    assert len([sql for sql in statements if f"from {model.__tablename__}" in sql]) == 2


def test_experiment_page_keeps_latest_owned_task_association(listing):
    service, model, list_page = listing
    if model is not Experiment:
        pytest.skip("Experiment-specific task association")
    seed(service, model, 200)
    with service._session() as session, session.begin():
        for task_id, owner, task_type in [
            ("a-old", "owner", "experiment"),
            ("b-latest", "owner", "experiment"),
            ("c-foreign", "other", "experiment"),
            ("d-wrong-type", "owner", "ab_test"),
        ]:
            session.add(
                AsyncTask(
                    id=task_id,
                    celery_task_id=task_id,
                    user_id=owner,
                    task_type=task_type,
                    entity_id="job-0020",
                    created_at=CREATED,
                )
            )
        session.add(
            AsyncTask(
                id="outside-page",
                celery_task_id="outside-page",
                user_id="owner",
                task_type="experiment",
                entity_id="job-0000",
                created_at=CREATED,
            )
        )
    items, total = list_page("owner", limit=20, offset=20)
    assert total == 200
    assert items[0]["task_id"] == "b-latest"
    assert all(item["task_id"] is None for item in items[1:])


@pytest.mark.parametrize("model", [Experiment, ABTest])
def test_public_config_sql_projects_snapshot_without_mutating_storage(tmp_path, model):
    from api.db import make_engine, make_session_factory, run_migrations

    engine = make_engine(f"sqlite:///{tmp_path}/projection.db")
    try:
        run_migrations(engine)
        factory = make_session_factory(engine)
        original = {
            "name": "original",
            "extra": [1, None],
            "dataset_snapshot": {
                "problems": [{"description": "private"}],
                "owner_id": "owner",
                "problem_count": 1,
                "extra": "keep",
            },
        }
        with factory() as session, session.begin():
            session.add(model(id="snapshot", user_id="owner", config=original))
        with factory() as session:
            public = session.scalar(select(public_dataset_config_sql(model.config, "sqlite")))
            assert public == {
                "name": "original",
                "extra": [1, None],
                "dataset_snapshot": {"problem_count": 1, "extra": "keep"},
            }
            assert session.scalar(select(model.config)) == original
    finally:
        engine.dispose()


@pytest.mark.parametrize("model", [Experiment, ABTest])
def test_public_config_sql_compiles_postgresql_jsonb_path_deletion(model):
    query = select(public_dataset_config_sql(model.config, "postgresql"))
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert f"CAST({model.__tablename__}.config AS JSONB)" in sql
    assert "#- ARRAY['dataset_snapshot', 'problems']" in sql
    assert "#- ARRAY['dataset_snapshot', 'owner_id']" in sql
