"""Database fixtures shared by the API and worker test suites."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from kiln_api.db.schema import metadata

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"
DEFAULT_URL = "postgresql+psycopg://kiln:kiln@127.0.0.1:5432/kiln_test"


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A fresh, migrated test database; fails loudly when Postgres is not running."""
    url = make_url(os.environ.get("KILN_TEST_DATABASE_URL", DEFAULT_URL))
    if not (url.database or "").endswith("_test"):
        pytest.fail(f"Refusing to recreate {url.database!r}: test databases must end in _test.")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as error:
        pytest.fail(f"Postgres is not reachable at {url.host}:{url.port}; run `make up`. ({error})")
    rendered = url.render_as_string(hide_password=False)
    command.upgrade(_alembic_config(rendered), "head")
    yield rendered
    admin.dispose()


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    with engine.begin() as connection:
        for table in reversed(metadata.sorted_tables):
            connection.execute(table.delete())
    engine.dispose()


@pytest.fixture
def alembic_config(database_url: str) -> Config:
    return _alembic_config(database_url)
