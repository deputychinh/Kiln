from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

from fakes import FakeStorage, FixedClock
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
    expected = f"http://storage.test/kiln-assets/thumbs/{asset_id}/{version_id}.webp"
    # One window, one URL for the same preview, wherever it appears (KILN-27).
    assert detail["versions"][0]["thumbnail_url"].startswith(f"{expected}?")
    assert detail["thumbnail_url"] == detail["versions"][0]["thumbnail_url"]
    assert listed["thumbnail_url"] == detail["thumbnail_url"]


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

    expected = f"http://storage.test/kiln-assets/thumbs/{asset_id}/{version_id}.webp"
    assert detail["kind"] == "model"
    assert detail["thumbnail_url"].startswith(f"{expected}?")
    assert detail["versions"][0]["thumbnail_url"] == detail["thumbnail_url"]
    assert version["thumbnail_url"] == detail["thumbnail_url"]


def _ready_asset_id(client: TestClient, storage: FakeStorage, engine: Engine) -> str:
    created = _created_and_completed(client, storage)
    asset_id, version_id = created["asset"]["id"], created["version"]["id"]
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE asset_versions SET status = 'ready' WHERE id = :id"), {"id": version_id}
        )
        connection.execute(
            text("UPDATE assets SET cover_version_id = :v WHERE id = :a"),
            {"v": version_id, "a": asset_id},
        )
    return str(asset_id)


def _preview_url(client: TestClient, asset_id: str) -> str:
    return str(client.get(f"/api/v1/assets/{asset_id}").json()["thumbnail_url"])


def test_a_preview_url_stays_the_same_for_its_window_and_changes_with_the_next(
    client: TestClient, storage: FakeStorage, engine: Engine, clock: FixedClock
) -> None:
    """KILN-27: the browser caches by URL, so a URL must not change on every request."""
    clock.current = datetime(2026, 11, 6, 8, 30, 0, tzinfo=UTC)  # a window start
    asset_id = _ready_asset_id(client, storage, engine)
    first = _preview_url(client, asset_id)

    clock.current = datetime(2026, 11, 6, 8, 39, 59, tzinfo=UTC)  # the window's last second
    same_window = _preview_url(client, asset_id)
    listed = client.get("/api/v1/assets").json()["items"][0]["thumbnail_url"]
    clock.current = datetime(2026, 11, 6, 8, 40, 0, tzinfo=UTC)  # the next window
    next_window = _preview_url(client, asset_id)

    assert same_window == first
    assert listed == first
    assert next_window != first
    assert parse_qs(urlsplit(first).query)["signed"] == ["2026-11-06T08:30:00+00:00"]
    assert parse_qs(urlsplit(next_window).query)["signed"] == ["2026-11-06T08:40:00+00:00"]


def test_a_preview_url_lives_25_minutes_and_is_privately_cacheable(
    client: TestClient, storage: FakeStorage, engine: Engine, clock: FixedClock
) -> None:
    """Handed out at the end of its window, a URL still has its 15 minutes (AC2, AC3)."""
    clock.current = datetime(2026, 11, 6, 8, 39, 59, tzinfo=UTC)
    url = _preview_url(client, _ready_asset_id(client, storage, engine))

    query = parse_qs(urlsplit(url).query)
    signed_at = datetime.fromisoformat(query["signed"][0])
    expires_at = signed_at + timedelta(seconds=int(query["ttl"][0]))
    assert expires_at - clock.now() >= timedelta(minutes=15)
    assert expires_at - signed_at == timedelta(minutes=25)
    assert query["cache"] == ["private, max-age=1500, immutable"]
