import pytest
from db_fixtures import database_url, engine
from fakes import FakeStorage, FixedClock

__all__ = ["database_url", "engine"]  # fixtures shared with the API suite


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()
