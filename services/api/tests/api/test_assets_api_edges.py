"""Boundary behaviour of the asset API: malformed input, limits, failures (KILN-3 review)."""

import logging
import threading
from collections.abc import Iterator
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
DECLARATION = {"file_name": "rock.png", "content_type": "image/png", "size_bytes": 2048}
ID_ROUTES = [
    ("get", "/api/v1/assets/{id}"),
    ("post", "/api/v1/assets/{id}/versions"),
    ("get", "/api/v1/asset-versions/{id}"),
    ("post", "/api/v1/asset-versions/{id}/completions"),
]


def _create(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/assets", json=ROCK)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.parametrize(("method", "path"), ID_ROUTES)
@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123", "00000000-0000-0000-0000"])
def test_a_malformed_id_is_a_validation_error_on_every_route(
    client: TestClient, method: str, path: str, bad_id: str
) -> None:
    url = path.format(id=bad_id)

    response = client.post(url, json=DECLARATION) if method == "post" else client.get(url)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({**DECLARATION, "content_type": "image/gif"}, "UNSUPPORTED_MEDIA_TYPE"),
        ({**DECLARATION, "size_bytes": 0}, "INVALID_FILE_SIZE"),
        ({**DECLARATION, "file_name": "."}, "INVALID_FILE_NAME"),
        ({**DECLARATION, "size_bytes": True}, "VALIDATION_FAILED"),
        ({**DECLARATION, "size_bytes": "10"}, "VALIDATION_FAILED"),
        ({**DECLARATION, "name": "extra"}, "VALIDATION_FAILED"),
        ({"file_name": "a.png"}, "VALIDATION_FAILED"),
    ],
)
def test_invalid_version_declarations_are_rejected_and_nothing_is_stored(
    client: TestClient, body: dict[str, Any], code: str
) -> None:
    asset_id = _create(client)["asset"]["id"]

    response = client.post(f"/api/v1/assets/{asset_id}/versions", json=body)

    assert response.status_code == 422
    assert response.json()["code"] == code
    assert len(client.get(f"/api/v1/assets/{asset_id}").json()["versions"]) == 1


def test_a_boolean_size_is_not_coerced_to_one(client: TestClient) -> None:
    response = client.post("/api/v1/assets", json={**ROCK, "size_bytes": True})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize("limit", [0, -5, 101, 100_000])
def test_a_limit_outside_one_to_a_hundred_is_rejected(client: TestClient, limit: int) -> None:
    response = client.get("/api/v1/assets", params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_a_body_over_one_megabyte_is_rejected_before_parsing(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assets",
        content=b'{"name": "' + b"x" * (1024 * 1024) + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_a_chunked_body_over_one_megabyte_is_rejected(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"name": "'
        for _ in range(65):
            yield b"x" * 16_384
        yield b'"}'

    response = client.post(
        "/api/v1/assets", content=chunks(), headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_a_file_replaced_between_check_and_copy_is_a_mismatch(
    client: TestClient, storage: FakeStorage
) -> None:
    created = _create(client)
    storage.put(created["upload"]["fields"]["key"], 2048, "image/png")
    storage.promote_succeeds = False
    version_id = created["version"]["id"]

    response = client.post(f"/api/v1/asset-versions/{version_id}/completions")

    assert response.status_code == 409
    assert response.json()["code"] == "UPLOAD_MISMATCH"
    assert client.get(f"/api/v1/asset-versions/{version_id}").json()["status"] == "pending_upload"


def test_a_completion_interrupted_after_the_copy_resumes_on_retry(
    client: TestClient, storage: FakeStorage
) -> None:
    created = _create(client)
    staging = created["upload"]["fields"]["key"]
    storage.put(staging, 2048, "image/png")
    storage.delete_available = False
    url = f"/api/v1/asset-versions/{created['version']['id']}/completions"

    interrupted = client.post(url)
    storage.delete_available = True
    resumed = client.post(url)

    assert interrupted.status_code == 503
    assert interrupted.headers["Retry-After"] == "1"
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "processing"
    assert staging not in storage.objects


def test_the_staging_key_is_not_the_final_key(client: TestClient, storage: FakeStorage) -> None:
    created = _create(client)
    staging = created["upload"]["fields"]["key"]
    storage.put(staging, 2048, "image/png")

    client.post(f"/api/v1/asset-versions/{created['version']['id']}/completions")

    assert staging.startswith("uploads/")
    assert [key for key in storage.objects if key.startswith("assets/")]


def test_a_held_row_lock_returns_database_busy_with_retry_after(
    database_url: str, engine: Engine
) -> None:
    settings = Settings(env=Environment.TEST, database_url=database_url, db_lock_timeout_ms=200)
    container = build_container(settings, storage=FakeStorage(), clock=FixedClock())
    with TestClient(create_app(settings, container=container)) as client:
        asset_id = _create(client)["asset"]["id"]
        locked = threading.Event()
        release = threading.Event()

        def hold_lock() -> None:
            with engine.begin() as connection:
                connection.execute(
                    text("SELECT id FROM assets WHERE id = :id FOR UPDATE"), {"id": asset_id}
                )
                locked.set()
                release.wait(5)

        holder = threading.Thread(target=hold_lock)
        holder.start()
        locked.wait(5)
        try:
            response = client.post(f"/api/v1/assets/{asset_id}/versions", json=DECLARATION)
        finally:
            release.set()
            holder.join()
        container.engine.dispose()

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_BUSY"
    assert response.headers["Retry-After"] == "1"


def test_a_database_outage_on_a_request_is_a_503_problem() -> None:
    settings = Settings(
        env=Environment.TEST, database_url="postgresql+psycopg://kiln:kiln@127.0.0.1:9/kiln_test"
    )
    container = build_container(settings, storage=FakeStorage(), clock=FixedClock())

    with TestClient(create_app(settings, container=container)) as client:
        response = client.get("/api/v1/assets")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"


def test_an_unexpected_error_is_a_500_problem_without_internals(
    client: TestClient, storage: FakeStorage
) -> None:
    created = _create(client)

    def explode() -> None:
        message = "secret internals"
        raise RuntimeError(message)

    storage.on_head = explode
    unsafe = TestClient(client.app, raise_server_exceptions=False)

    response = unsafe.post(f"/api/v1/asset-versions/{created['version']['id']}/completions")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "INTERNAL"
    assert "secret" not in response.text


def _final_key(engine: Engine, version_id: str) -> str:
    with engine.connect() as connection:
        key: str = connection.execute(
            text("SELECT object_key FROM asset_versions WHERE id = :id"), {"id": version_id}
        ).scalar_one()
    return key


def test_a_resumed_completion_still_checks_the_final_file(
    client: TestClient, storage: FakeStorage, engine: Engine
) -> None:
    created = _create(client)
    version_id = created["version"]["id"]
    storage.put(_final_key(engine, version_id), 9, "image/png")

    response = client.post(f"/api/v1/asset-versions/{version_id}/completions")

    assert response.status_code == 409
    assert response.json()["code"] == "UPLOAD_MISMATCH"


def test_a_completion_resumes_when_only_the_final_file_remains(
    client: TestClient, storage: FakeStorage, engine: Engine
) -> None:
    created = _create(client)
    version_id = created["version"]["id"]
    storage.put(
        _final_key(engine, version_id), 2048, "image/png"
    )  # promoted and staging deleted, status not saved

    response = client.post(f"/api/v1/asset-versions/{version_id}/completions")

    assert response.status_code == 200
    assert response.json()["status"] == "processing"


ORIGIN = {"Origin": "http://127.0.0.1:5173", "X-Request-Id": "req-42"}


def test_a_browser_may_send_an_idempotency_key_across_origins(client: TestClient) -> None:
    """The web app uploads with `Idempotency-Key` (KILN-26), so the preflight must allow it."""
    response = client.options(
        "/api/v1/assets",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key",
        },
    )

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed
    assert "content-type" in allowed


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_the_local_web_app_may_call_the_api_from_either_host_name(
    client: TestClient, origin: str
) -> None:
    """`make web` prints `localhost`; a browser on either name must not be blocked by CORS."""
    response = client.get("/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_a_413_keeps_cors_and_the_request_id(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assets",
        content=b"x" * (1024 * 1024 + 1),
        headers={**ORIGIN, "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert response.headers["X-Request-Id"] == "req-42"


def test_a_500_keeps_cors_and_the_request_id_and_logs_it(
    client: TestClient, storage: FakeStorage, caplog: pytest.LogCaptureFixture
) -> None:
    created = _create(client)

    def explode() -> None:
        message = "boom"
        raise RuntimeError(message)

    storage.on_head = explode
    with caplog.at_level(logging.ERROR, logger="kiln_api"):
        response = client.post(
            f"/api/v1/asset-versions/{created['version']['id']}/completions", headers=ORIGIN
        )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert response.headers["X-Request-Id"] == "req-42"
    assert "request req-42" in caplog.text


@pytest.mark.parametrize(
    ("final_size", "code"), [(None, "UPLOAD_NOT_FOUND"), (9, "UPLOAD_MISMATCH")]
)
def test_a_source_gone_during_promotion_still_checks_the_final_file(
    client: TestClient, storage: FakeStorage, engine: Engine, final_size: int | None, code: str
) -> None:
    created = _create(client)
    version_id = created["version"]["id"]
    storage.put(created["upload"]["fields"]["key"], 2048, "image/png")
    storage.force_source_gone = True
    if final_size is not None:
        storage.put(_final_key(engine, version_id), final_size, "image/png")

    response = client.post(f"/api/v1/asset-versions/{version_id}/completions")

    assert response.status_code == 409
    assert response.json()["code"] == code
