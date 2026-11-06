from typing import Any

from fakes import FakeStorage
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

ROCK = {"name": "Rock", "file_name": "rock.png", "content_type": "image/png", "size_bytes": 4}


def _created_and_completed(client: TestClient, storage: FakeStorage) -> dict[str, Any]:
    created: dict[str, Any] = client.post("/api/v1/assets", json=ROCK).json()
    storage.put(created["upload"]["fields"]["key"], 4, "image/png", b"\x89PNG")
    client.post(f"/api/v1/asset-versions/{created['version']['id']}/completions")
    return created


def test_completion_records_the_etag_and_queues_one_thumbnail_job(
    client: TestClient, storage: FakeStorage, engine: Engine
) -> None:
    created = _created_and_completed(client, storage)
    version_id = created["version"]["id"]
    client.post(f"/api/v1/asset-versions/{version_id}/completions")  # idempotent repeat

    with engine.connect() as connection:
        etag, final_key = connection.execute(
            text("SELECT etag, object_key FROM asset_versions WHERE id = :id"), {"id": version_id}
        ).one()
        jobs = connection.execute(
            text("SELECT kind, status, attempts FROM jobs WHERE version_id = :id"),
            {"id": version_id},
        ).all()

    assert etag == storage.objects[final_key].etag
    assert [tuple(job) for job in jobs] == [("thumbnail", "queued", 0)]


def test_a_failed_completion_queues_nothing(client: TestClient, engine: Engine) -> None:
    created = client.post("/api/v1/assets", json=ROCK).json()

    client.post(f"/api/v1/asset-versions/{created['version']['id']}/completions")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0


def test_versions_and_assets_expose_thumbnails_only_when_ready(
    client: TestClient, storage: FakeStorage, engine: Engine
) -> None:
    created = _created_and_completed(client, storage)
    asset_id, version_id = created["asset"]["id"], created["version"]["id"]
    processing = client.get(f"/api/v1/assets/{asset_id}").json()

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE asset_versions SET status = 'ready' WHERE id = :id"), {"id": version_id}
        )
        connection.execute(
            text("UPDATE assets SET cover_version_id = :v WHERE id = :a"),
            {"v": version_id, "a": asset_id},
        )
    detail = client.get(f"/api/v1/assets/{asset_id}").json()
    listed = client.get("/api/v1/assets").json()["items"][0]

    assert processing["thumbnail_url"] is None
    assert processing["versions"][0]["thumbnail_url"] is None
    expected = f"http://storage.test/kiln-assets/thumbs/{asset_id}/{version_id}.webp?ttl=900"
    assert detail["versions"][0]["thumbnail_url"] == expected
    assert detail["thumbnail_url"] == expected
    assert listed["thumbnail_url"] == expected


def test_a_failed_version_shows_its_reason(
    client: TestClient, storage: FakeStorage, engine: Engine
) -> None:
    created = _created_and_completed(client, storage)
    version_id = created["version"]["id"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE asset_versions SET status = 'failed', failure_reason = 'UNREADABLE_IMAGE'"
                " WHERE id = :id"
            ),
            {"id": version_id},
        )

    version = client.get(f"/api/v1/asset-versions/{version_id}").json()

    assert version["status"] == "failed"
    assert version["failure_reason"] == "UNREADABLE_IMAGE"
    assert version["thumbnail_url"] is None


def test_models_expose_their_previews_like_images(
    client: TestClient, storage: FakeStorage, engine: Engine
) -> None:
    model = {"name": "Crate", "file_name": "crate.glb", "content_type": "model/gltf-binary"}
    created: dict[str, Any] = client.post("/api/v1/assets", json={**model, "size_bytes": 4}).json()
    storage.put(created["upload"]["fields"]["key"], 4, "model/gltf-binary", b"glTF")
    asset_id, version_id = created["asset"]["id"], created["version"]["id"]
    client.post(f"/api/v1/asset-versions/{version_id}/completions")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE asset_versions SET status = 'ready' WHERE id = :id"), {"id": version_id}
        )
        connection.execute(
            text("UPDATE assets SET cover_version_id = :v WHERE id = :a"),
            {"v": version_id, "a": asset_id},
        )

    detail = client.get(f"/api/v1/assets/{asset_id}").json()
    version = client.get(f"/api/v1/asset-versions/{version_id}").json()

    expected = f"http://storage.test/kiln-assets/thumbs/{asset_id}/{version_id}.webp?ttl=900"
    assert detail["kind"] == "model"
    assert detail["thumbnail_url"] == expected
    assert detail["versions"][0]["thumbnail_url"] == expected
    assert version["thumbnail_url"] == expected
