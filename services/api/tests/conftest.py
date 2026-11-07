from collections.abc import Iterator

import pytest
from db_fixtures import alembic_config, database_url, engine, principal, user
from fakes import FakeStorage, FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from kiln_api.config import Settings
from kiln_api.container import build_container
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
def client(
    database_url: str, engine: Engine, storage: FakeStorage, clock: FixedClock
) -> Iterator[TestClient]:
    settings = Settings(env=Environment.TEST, database_url=database_url)
    container = build_container(settings, engine=engine, storage=storage, clock=clock)
    with TestClient(create_app(settings, container=container)) as test_client:
        yield test_client
