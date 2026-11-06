import time
from collections.abc import Iterator

import pytest
from fakes import FakeStorage, FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from kiln_api.config import Settings
from kiln_api.container import build_container, guard_storage
from kiln_api.enums import Environment
from kiln_api.main import create_app


@pytest.fixture
def guarded_client(
    database_url: str, engine: Engine, storage: FakeStorage, clock: FixedClock
) -> Iterator[TestClient]:
    settings = Settings(
        env=Environment.TEST,
        database_url=database_url,
        storage_breaker_failures=2,
        storage_breaker_cooldown_seconds=30,
    )
    container = build_container(
        settings, engine=engine, storage=guard_storage(storage, settings), clock=clock
    )
    with TestClient(create_app(settings, container=container)) as test_client:
        yield test_client


def _pending_version(client: TestClient) -> str:
    created = client.post(
        "/api/v1/assets",
        json={
            "name": "Rock",
            "file_name": "rock.png",
            "content_type": "image/png",
            "size_bytes": 10,
        },
    )
    assert created.status_code == 201
    return str(created.json()["version"]["id"])


def test_an_open_circuit_answers_503_at_once_with_the_cooldown_as_retry_after(
    guarded_client: TestClient, storage: FakeStorage
) -> None:
    version_id = _pending_version(guarded_client)
    storage.available = False
    for _ in range(2):
        failed = guarded_client.post(f"/api/v1/asset-versions/{version_id}/completions")
        assert failed.status_code == 503
        assert failed.headers["Retry-After"] == "1"

    started = time.monotonic()
    fast = guarded_client.post(f"/api/v1/asset-versions/{version_id}/completions")
    elapsed = time.monotonic() - started

    assert fast.status_code == 503
    assert fast.json()["code"] == "STORAGE_UNAVAILABLE"
    assert fast.json()["detail"] == "File storage is unavailable; try again shortly."
    assert int(fast.headers["Retry-After"]) in range(29, 31)
    assert "CIRCUIT_OPEN" not in fast.text  # the cause stays in the logs
    assert elapsed < 0.5


def test_with_the_circuit_open_ready_fails_and_pages_that_only_sign_urls_still_work(
    guarded_client: TestClient, storage: FakeStorage
) -> None:
    _pending_version(guarded_client)
    storage.available = False
    for _ in range(2):
        guarded_client.get("/ready")

    assert guarded_client.get("/ready").status_code == 503
    assert guarded_client.get("/health").status_code == 200
    listing = guarded_client.get("/api/v1/assets")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    created = guarded_client.post(
        "/api/v1/assets",
        json={
            "name": "Tree",
            "file_name": "tree.png",
            "content_type": "image/png",
            "size_bytes": 5,
        },
    )
    assert created.status_code == 201  # creating signs an upload form locally


def test_the_container_guards_real_storage_by_default(database_url: str, engine: Engine) -> None:
    settings = Settings(env=Environment.TEST, database_url=database_url)

    container = build_container(settings, engine=engine)

    assert type(container.storage).__name__ == "GuardedStorage"
