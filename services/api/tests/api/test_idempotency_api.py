import threading
from datetime import timedelta
from typing import Any

import pytest
from fakes import FakeStorage, FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from kiln_api.config import Settings
from kiln_api.container import build_container
from kiln_api.enums import Environment
from kiln_api.main import create_app

ROCK = {"name": "Rock", "file_name": "rock.png", "content_type": "image/png", "size_bytes": 2048}
V2 = {"file_name": "rock_v2.png", "content_type": "image/png", "size_bytes": 10}
KEY = '"8e03978e-40d5-43e8-bc93-6894a57f9324"'


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())  # noqa: S608 - fixed names


def _post(client: TestClient, url: str, body: dict[str, Any], key: str | None = KEY) -> Any:
    headers = {"Idempotency-Key": key} if key is not None else {}
    return client.post(url, json=body, headers=headers)


def test_a_retried_creation_replays_the_same_asset_with_a_fresh_upload(
    client: TestClient, engine: Engine, clock: FixedClock
) -> None:
    first = _post(client, "/api/v1/assets", ROCK)
    clock.advance(60)
    second = _post(client, "/api/v1/assets", ROCK)

    assert first.status_code == second.status_code == 201
    assert "Idempotent-Replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.headers["Location"] == first.headers["Location"]
    assert second.json()["asset"] == first.json()["asset"]
    assert second.json()["version"] == first.json()["version"]
    assert second.json()["upload"]["fields"]["key"] == first.json()["upload"]["fields"]["key"]
    assert second.json()["upload"]["expires_at"] > first.json()["upload"]["expires_at"]
    assert _count(engine, "assets") == 1


def test_a_retried_new_version_replays_the_same_number(client: TestClient, engine: Engine) -> None:
    asset_id = _post(client, "/api/v1/assets", ROCK, key=None).json()["asset"]["id"]
    url = f"/api/v1/assets/{asset_id}/versions"

    first = _post(client, url, V2)
    second = _post(client, url, V2)

    assert first.status_code == second.status_code == 201
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["version"]["number"] == first.json()["version"]["number"] == 2
    assert second.headers["Location"] == first.headers["Location"]
    assert _count(engine, "asset_versions") == 2


def test_a_key_reused_with_another_body_is_rejected(client: TestClient, engine: Engine) -> None:
    _post(client, "/api/v1/assets", ROCK)

    response = _post(client, "/api/v1/assets", {**ROCK, "name": "Other"})

    assert response.status_code == 422
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert _count(engine, "assets") == 1


def test_a_key_reused_on_another_endpoint_is_rejected(client: TestClient, engine: Engine) -> None:
    created = _post(client, "/api/v1/assets", ROCK).json()
    asset_id = created["asset"]["id"]

    response = _post(client, f"/api/v1/assets/{asset_id}/versions", V2)

    assert response.status_code == 422
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert _count(engine, "asset_versions") == 1


def test_concurrent_duplicates_wait_and_all_get_the_same_asset(
    client: TestClient, engine: Engine
) -> None:
    barrier = threading.Barrier(6)
    results: list[tuple[int, str]] = []

    def send() -> None:
        barrier.wait()
        response = _post(client, "/api/v1/assets", ROCK)
        results.append((response.status_code, response.json()["asset"]["id"]))

    threads = [threading.Thread(target=send) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert {status for status, _ in results} == {201}
    assert len({asset_id for _, asset_id in results}) == 1
    assert _count(engine, "assets") == 1


def test_a_key_held_longer_than_the_lock_timeout_is_in_use(
    database_url: str, engine: Engine
) -> None:
    settings = Settings(env=Environment.TEST, database_url=database_url, db_lock_timeout_ms=200)
    container = build_container(settings, storage=FakeStorage(), clock=FixedClock())
    holding = threading.Event()
    release = threading.Event()

    def hold_key() -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO idempotency_keys (key, operation, request_hash, created_at)"
                    " VALUES (:key, 'create_asset', :hash, now())"
                ),
                {"key": KEY.strip('"'), "hash": b"\x00" * 32},
            )
            holding.set()
            release.wait(5)

    holder = threading.Thread(target=hold_key)
    holder.start()
    holding.wait(5)
    try:
        with TestClient(create_app(settings, container=container)) as client:
            response = _post(client, "/api/v1/assets", ROCK)
    finally:
        release.set()
        holder.join()
        container.engine.dispose()

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_KEY_IN_USE"


@pytest.mark.parametrize("key", ["", '"', '"unterminated', "has space", "k" * 256, "café"])
def test_an_invalid_key_is_a_400(client: TestClient, engine: Engine, key: str) -> None:
    response = client.post(
        "/api/v1/assets", json=ROCK, headers={b"Idempotency-Key": key.encode("latin-1")}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IDEMPOTENCY_KEY"
    assert _count(engine, "assets") == 0


def test_without_a_key_every_request_creates(client: TestClient, engine: Engine) -> None:
    _post(client, "/api/v1/assets", ROCK, key=None)
    _post(client, "/api/v1/assets", ROCK, key=None)

    assert _count(engine, "assets") == 2


def test_a_failed_request_does_not_store_the_key(client: TestClient, engine: Engine) -> None:
    failed = _post(client, "/api/v1/assets", {**ROCK, "content_type": "image/gif"})
    fixed = _post(client, "/api/v1/assets", ROCK)

    assert failed.status_code == 422
    assert fixed.status_code == 201
    assert "Idempotent-Replayed" not in fixed.headers
    assert _count(engine, "idempotency_keys") == 1


def test_an_expired_key_is_treated_as_new(
    client: TestClient, engine: Engine, clock: FixedClock
) -> None:
    first = _post(client, "/api/v1/assets", ROCK).json()
    clock.advance(timedelta(hours=24, seconds=1).total_seconds())

    second = _post(client, "/api/v1/assets", {**ROCK, "name": "Other"})

    assert second.status_code == 201
    assert second.json()["asset"]["id"] != first["asset"]["id"]
    assert _count(engine, "assets") == 2
    assert _count(engine, "idempotency_keys") == 1
