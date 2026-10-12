"""Business database layer for the API (issue #151).

SQLAlchemy models plus Alembic-managed migrations, physically isolated from
the authentication store (``api/auth/store.py``). The engine targets SQLite
in development and connects to PostgreSQL through ``DATABASE_URL``.
"""

from api.db.engine import business_database_url, make_engine, make_session_factory
from api.db.migrate import downgrade, offline_upgrade_sql, run_migrations, upgrade
from api.db.models import Base, Evaluation, EvaluationResult, Problem
from api.db.problem_store import ProblemStore

__all__ = [
    "Base",
    "Evaluation",
    "EvaluationResult",
    "Problem",
    "ProblemStore",
    "business_database_url",
    "downgrade",
    "make_engine",
    "make_session_factory",
    "offline_upgrade_sql",
    "run_migrations",
    "upgrade",
]
