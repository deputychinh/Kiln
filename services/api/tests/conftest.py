from collections.abc import Iterator

import pytest
from db_fixtures import (
    APP_HEADERS,
    TEST_HASHER,
    alembic_config,
    database_url,
    engine,
    insert_session,
    insert_token,
    principal,
    user,
)
from fakes import FakeStorage, FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from kiln_api.config import Settings
from kiln_api.constants import SESSION_COOKIE_LOCAL
from kiln_api.container import build_container
from kiln_api.domain.identity import User
from kiln_api.enums import Environment
from kiln_api.main import create_app

# Fixtures re-exported for pytest.
__all__ = ["alembic_config", "database_url", "engine", "principal", "user"]


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def anonymous_client(
    database_url: str, engine: Engine, storage: FakeStorage, clock: FixedClock
) -> Iterator[TestClient]:
    """The app with no session or token (the web app's headers, but signed out)."""
    settings = Settings(env=Environment.TEST, database_url=database_url)
    container = build_container(
        settings, engine=engine, storage=storage, clock=clock, hasher=TEST_HASHER
    )
    with TestClient(create_app(settings, container=container), headers=APP_HEADERS) as test_client:
        yield test_client


@pytest.fixture
def client(
    anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> TestClient:
    """Calls as `user` with a read and write access token, as the CLI does.

    A token outlives the clock jumps of the 24-hour tests; `session_client` is the browser.
    """
    anonymous_client.headers["Authorization"] = (
        f"Bearer {insert_token(engine, user, now=clock.now())}"
    )
    return anonymous_client


@pytest.fixture
def session_client(
    anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> TestClient:
    """Signed in as `user` through a browser session, with the web app's CSRF headers."""
    anonymous_client.cookies.set(
        SESSION_COOKIE_LOCAL, insert_session(engine, user, now=clock.now())
    )
    return anonymous_client
