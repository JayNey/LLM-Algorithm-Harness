"""Engine and session factory for the business database."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

DATABASE_PATH = Path("data/business/business.sqlite3")


def business_database_url() -> str:
    """Resolve the business database URL from settings or the local default."""
    from api.config import settings

    return settings.DATABASE_URL or f"sqlite:///{DATABASE_PATH}"


def make_engine(database_url: str) -> Engine:
    """Create an engine suited to the configured database URL.

    SQLite gets cross-thread access plus a busy timeout so API worker threads
    and the execution thread can share one file without spurious locks.
    File-based SQLite databases get their parent directory created upfront.
    """
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" not in database_url:
            Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, future=True, connect_args=connect_args)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory producing short-lived, transactional sessions."""
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


# Global session factory, initialized by app startup
_SessionLocal: sessionmaker[Session] | None = None


def set_session_factory(session_factory: sessionmaker[Session]) -> None:
    """Set the global session factory (called during app startup)."""
    global _SessionLocal
    _SessionLocal = session_factory


def get_db() -> Session:
    """Dependency to get a database session for FastAPI endpoints."""
    if _SessionLocal is None:
        raise RuntimeError("Database session factory not initialized")
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
