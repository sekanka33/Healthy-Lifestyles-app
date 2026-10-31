"""Migrations must build exactly the schema the models describe, and be reversible.

Runs against SQLite by default. Set TEST_POSTGRES_URL (an empty, disposable database!)
to also run against PostgreSQL, which is what production uses.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from app.db.base import Base

BACKEND = Path(__file__).resolve().parents[1]

URLS = []
if os.environ.get("TEST_POSTGRES_URL"):
    URLS.append(os.environ["TEST_POSTGRES_URL"])


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(params=["sqlite"] + URLS)
def db_url(request, tmp_path):
    if request.param == "sqlite":
        return f"sqlite:///{tmp_path / 'migrations.db'}"
    return request.param


def test_upgrade_matches_models_and_downgrade_is_clean(db_url):
    cfg = _config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Models and migrations disagree: {diff}"

    command.downgrade(cfg, "base")
    remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert remaining == set()
    engine.dispose()
