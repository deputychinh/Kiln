import logging

import pytest
from fakes import FakeStorage, FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from kiln_api.config import Settings
from kiln_api.container import build_container
from kiln_api.enums import Environment
from kiln_api.main import create_app

UNREACHABLE_DB = "postgresql+psycopg://kiln:kiln@127.0.0.1:9/kiln_test"


def test_an_unreachable_database_makes_ready_fail_with_a_stable_code() -> None:
    settings = Settings(env=Environment.TEST, database_url=UNREACHABLE_DB)
    container = build_container(settings, storage=FakeStorage(), clock=FixedClock())

    with TestClient(create_app(settings, container=container)) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"


def test_the_api_starts_when_storage_is_down_and_logs_a_warning(
    database_url: str, engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    storage = FakeStorage()
    storage.available = False
    settings = Settings(env=Environment.TEST, database_url=database_url)
    container = build_container(settings, engine=engine, storage=storage, clock=FixedClock())

    with (
        caplog.at_level(logging.WARNING, logger="kiln_api"),
        TestClient(create_app(settings, container=container)) as client,
    ):
        health = client.get("/health")

    assert health.status_code == 200
    assert "storage unavailable at start-up" in caplog.text
