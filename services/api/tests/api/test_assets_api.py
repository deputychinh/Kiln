from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from fakes import FakeStorage, FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from kiln_api.domain.ids import uuid7

ROCK = {
    "name": "Rock",
    "file_name": "T_Rock_01_BaseColor.png",
    "content_type": "image/png",
    "size_bytes": 2048,
}


def _create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/v1/assets", json={**ROCK, **overrides})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _upload(storage: FakeStorage, created: dict[str, Any], **overrides: Any) -> None:
    fields = created["upload"]["fields"]
    storage.put(
        fields["key"],
        overrides.get("size", created["version"]["size_bytes"]),
        overrides.get("content_type", created["version"]["content_type"]),
    )


def test_creating_an_asset_returns_version_one_and_a_signed_upload(
    client: TestClient, storage: FakeStorage, clock: FixedClock
) -> None:
    response = client.post("/api/v1/assets", json=ROCK)

    assert response.status_code == 201
    body = response.json()
    assert response.headers["Location"] == f"/api/v1/assets/{body['asset']['id']}"
    assert body["asset"]["name"] == "Rock"
    assert body["asset"]["kind"] == "image"
    assert body["version"]["number"] == 1
    assert body["version"]["status"] == "pending_upload"
    assert "object_key" not in body["version"]
    expires = body["upload"]["expires_at"].replace("Z", "+00:00")
    assert expires == (clock.now() + timedelta(minutes=15)).isoformat()
    assert storage.signed == [
        {
            "key": body["upload"]["fields"]["key"],
            "content_type": "image/png",
            "size": 2048,
            "ttl": 900,
        }
    ]


def test_completing_an_upload_starts_processing_and_is_idempotent(
    client: TestClient, storage: FakeStorage
) -> None:
    created = _create(client)
    _upload(storage, created)
    url = f"/api/v1/asset-versions/{created['version']['id']}/completions"

    first = client.post(url)
    second = client.post(url)

    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "processing"
    assert second.json() == first.json()


def test_completing_without_an_upload_is_a_conflict(client: TestClient) -> None:
    created = _create(client)
    version_id = created["version"]["id"]

    response = client.post(f"/api/v1/asset-versions/{version_id}/completions")

    assert response.status_code == 409
    assert response.json()["code"] == "UPLOAD_NOT_FOUND"
    assert client.get(f"/api/v1/asset-versions/{version_id}").json()["status"] == "pending_upload"


@pytest.mark.parametrize(
    "mismatch", [{"size": 2047}, {"size": 2049}, {"content_type": "image/jpeg"}]
)
def test_completing_a_mismatched_upload_is_a_conflict(
    client: TestClient, storage: FakeStorage, mismatch: dict[str, Any]
) -> None:
    created = _create(client)
    _upload(storage, created, **mismatch)
    version_id = created["version"]["id"]

    response = client.post(f"/api/v1/asset-versions/{version_id}/completions")

    assert response.status_code == 409
    assert response.json()["code"] == "UPLOAD_MISMATCH"
    assert client.get(f"/api/v1/asset-versions/{version_id}").json()["status"] == "pending_upload"


def test_a_storage_outage_during_completion_is_a_503(
    client: TestClient, storage: FakeStorage
) -> None:
    created = _create(client)
    storage.available = False

    response = client.post(f"/api/v1/asset-versions/{created['version']['id']}/completions")

    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"


def test_adding_a_version_returns_the_next_number_and_its_own_upload(client: TestClient) -> None:
    created = _create(client)
    asset_id = created["asset"]["id"]

    response = client.post(
        f"/api/v1/assets/{asset_id}/versions",
        json={"file_name": "rock_v2.png", "content_type": "image/png", "size_bytes": 10},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version"]["number"] == 2
    assert response.headers["Location"] == f"/api/v1/asset-versions/{body['version']['id']}"
    assert body["upload"]["fields"]["key"] != created["upload"]["fields"]["key"]
    assert client.get(response.headers["Location"]).json()["number"] == 2


def test_a_version_of_another_kind_is_rejected(client: TestClient) -> None:
    created = _create(client)

    response = client.post(
        f"/api/v1/assets/{created['asset']['id']}/versions",
        json={"file_name": "rock.glb", "content_type": "model/gltf-binary", "size_bytes": 10},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ASSET_KIND_MISMATCH"


def test_listing_pages_newest_first_and_detail_lists_versions(
    client: TestClient, clock: FixedClock
) -> None:
    ids = []
    for index in range(3):
        ids.append(_create(client, name=f"Asset {index}")["asset"]["id"])
        clock.advance(1)

    first = client.get("/api/v1/assets", params={"limit": 2}).json()
    second = client.get(
        "/api/v1/assets", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    detail = client.get(f"/api/v1/assets/{ids[0]}").json()

    assert [a["id"] for a in first["items"] + second["items"]] == list(reversed(ids))
    assert second["next_cursor"] is None
    assert [v["number"] for v in detail["versions"]] == [1]


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({**ROCK, "name": "   "}, 422, "INVALID_ASSET_NAME"),
        ({**ROCK, "content_type": "image/gif"}, 422, "UNSUPPORTED_MEDIA_TYPE"),
        ({**ROCK, "size_bytes": 0}, 422, "INVALID_FILE_SIZE"),
        ({**ROCK, "file_name": ".."}, 422, "INVALID_FILE_NAME"),
        ({k: v for k, v in ROCK.items() if k != "name"}, 422, "VALIDATION_FAILED"),
        ({**ROCK, "size_bytes": "big"}, 422, "VALIDATION_FAILED"),
        ({**ROCK, "extra": True}, 422, "VALIDATION_FAILED"),
        ({**ROCK, "name": "x" * 1001}, 422, "VALIDATION_FAILED"),
    ],
)
def test_invalid_creations_are_rejected_and_nothing_is_stored(
    client: TestClient, body: dict[str, Any], status: int, code: str
) -> None:
    response = client.post("/api/v1/assets", json=body)

    assert response.status_code == status
    assert response.json()["code"] == code
    assert client.get("/api/v1/assets").json()["items"] == []


@pytest.mark.parametrize(
    ("method", "path", "code"),
    [
        ("get", "/api/v1/assets/{id}", "ASSET_NOT_FOUND"),
        ("post", "/api/v1/assets/{id}/versions", "ASSET_NOT_FOUND"),
        ("get", "/api/v1/asset-versions/{id}", "ASSET_VERSION_NOT_FOUND"),
        ("post", "/api/v1/asset-versions/{id}/completions", "ASSET_VERSION_NOT_FOUND"),
    ],
)
def test_unknown_ids_are_404_with_a_stable_code(
    client: TestClient, method: str, path: str, code: str
) -> None:
    body = {"file_name": "a.png", "content_type": "image/png", "size_bytes": 1}
    url = path.format(id=uuid7())

    response = client.post(url, json=body) if method == "post" else client.get(url)

    assert response.status_code == 404
    assert response.json()["code"] == code


def test_a_malformed_id_is_a_validation_error(client: TestClient) -> None:
    response = client.get("/api/v1/assets/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_a_malformed_cursor_is_a_400(client: TestClient) -> None:
    response = client.get("/api/v1/assets", params={"cursor": "nope"})

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_CURSOR"


def test_responses_carry_uuid_v7_ids(client: TestClient) -> None:
    created = _create(client)

    assert UUID(created["asset"]["id"]).version == 7


def test_a_completion_that_loses_a_race_returns_the_winner_s_result(
    client: TestClient, storage: FakeStorage, engine: Engine
) -> None:
    created = _create(client)
    _upload(storage, created)
    version_id = created["version"]["id"]

    def finish_elsewhere() -> None:
        storage.on_head = None
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE asset_versions SET status = 'processing' WHERE id = :id"),
                {"id": version_id},
            )

    storage.on_head = finish_elsewhere
    response = client.post(f"/api/v1/asset-versions/{version_id}/completions")

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
