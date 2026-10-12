"""Programmatic Alembic entry points for the business database.

The application runs ``run_migrations`` on startup, so no alembic.ini is
required; the command-line equivalent is::

    alembic -c api/db/alembic.ini upgrade head
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

SCRIPT_LOCATION = Path(__file__).resolve().parent / "migrations"


def _alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _target_url(database_url: str | Engine) -> str:
    if isinstance(database_url, str):
        return database_url
    return database_url.url.render_as_string(hide_password=False)


def upgrade(database_url: str | Engine, revision: str = "head") -> None:
    """Upgrade the business database to ``revision`` (default latest)."""
    command.upgrade(_alembic_config(_target_url(database_url)), revision)


def downgrade(database_url: str | Engine, revision: str = "base") -> None:
    """Downgrade the business database to ``revision`` (default base)."""
    command.downgrade(_alembic_config(_target_url(database_url)), revision)


def run_migrations(engine_or_url: str | Engine) -> None:
    """Bring the business database up to the latest migration."""
    upgrade(engine_or_url)


def offline_upgrade_sql(database_url: str, revision: str = "head") -> str:
    """Render the upgrade SQL for ``database_url`` without connecting.

    Used to verify migration portability across dialects (e.g. PostgreSQL)
    from CI without provisioning a database server.
    """
    buffer = StringIO()
    cfg = _alembic_config(database_url)
    cfg.attributes["output_buffer"] = buffer
    command.upgrade(cfg, revision, sql=True)
    return buffer.getvalue()
