"""Database fixtures shared by the API and worker test suites."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from kiln_api.adapters import Argon2PasswordHasher
from kiln_api.constants import CSRF_HEADER, CSRF_HEADER_VALUE, SESSION_COOKIE_LOCAL
from kiln_api.db.schema import metadata
from kiln_api.domain.identity import (
    Principal,
    User,
    new_access_token,
    new_session,
    session_principal,
)
from kiln_api.domain.ids import uuid7
from kiln_api.enums import AuthMethod, Scope
from kiln_api.repositories.identity import SqlIdentityStore

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


# --- identity (KILN-12) --------------------------------------------------------------------------
# Cheap Argon2id for tests (the production parameters are pinned in test_password_hashing.py).
TEST_PASSWORD = "correct horse battery staple"  # noqa: S105 - a test fixture, never deployed
TEST_HASHER = Argon2PasswordHasher(memory_kib=64, time_cost=1, parallelism=1)
_TEST_HASH = TEST_HASHER.hash(TEST_PASSWORD)
_STAMP = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)


def insert_user(
    engine: Engine, *, email: str = "ada@kiln.test", display_name: str = "Ada Artist"
) -> User:
    """A user whose password is `TEST_PASSWORD`, stored straight in the database."""
    user = User(
        id=uuid7(),
        email=email,
        display_name=display_name,
        password_hash=_TEST_HASH,
        created_at=_STAMP,
        updated_at=_STAMP,
    )
    SqlIdentityStore(engine).add_user(user)
    return user


def insert_session(engine: Engine, user: User, *, now: datetime) -> str:
    """A live session for `user`; returns the cookie value."""
    raw, session = new_session(user.id, now=now)
    SqlIdentityStore(engine).add_session(session)
    return raw


def insert_token(
    engine: Engine,
    user: User,
    *,
    now: datetime,
    scopes: frozenset[Scope] = frozenset(Scope),
    expires_in_days: int = 365,
) -> str:
    """A personal access token for `user`; returns the secret."""
    secret, token = new_access_token(
        user.id,
        name="Test token",
        scopes=scopes,
        expires_in_days=expires_in_days,
        now=now,
        new_id=uuid7,
    )
    SqlIdentityStore(engine).add_token(token)
    return secret


def principal_of(user: User, scopes: frozenset[Scope] | None = None) -> Principal:
    """A session principal, or a token principal with `scopes`."""
    if scopes is None:
        return session_principal(user)
    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        method=AuthMethod.TOKEN,
        scopes=scopes,
    )


@pytest.fixture
def user(engine: Engine) -> User:
    return insert_user(engine)


@pytest.fixture
def principal(user: User) -> Principal:
    return principal_of(user)


APP_ORIGIN = "http://127.0.0.1:5173"
# What the web app sends with every write (KILN-12 CSRF check).
APP_HEADERS = {CSRF_HEADER: CSRF_HEADER_VALUE, "Origin": APP_ORIGIN}


def sign_in_client(client: TestClient, engine: Engine, user: User, *, now: datetime) -> TestClient:
    """Give a test client `user`'s session cookie and the web app's CSRF headers."""
    client.headers.update(APP_HEADERS)
    client.cookies.set(SESSION_COOKIE_LOCAL, insert_session(engine, user, now=now))
    return client


def artist(engine: Engine) -> Principal:
    """The default test user's session principal, created on first use in this database."""
    found = SqlIdentityStore(engine).user_by_email("ada@kiln.test")
    return principal_of(found or insert_user(engine))
