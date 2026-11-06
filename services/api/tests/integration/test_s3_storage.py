"""Against the real SeaweedFS from `make up` (ADR 0003): the signed POST policy and HEAD."""

import io
import socket
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from itertools import chain

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from kiln_api.adapters import S3ObjectStorage
from kiln_api.config import Settings
from kiln_api.container import build_container, build_storage, guard_storage
from kiln_api.enums import Environment, PromotionResult
from kiln_api.errors import StorageUnavailableError
from kiln_api.main import create_app


def _closed_port() -> int:
    """A local port with nothing listening (bound, then released)."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def settings(database_url: str) -> Settings:
    # One shared bucket: every SeaweedFS bucket reserves its own volumes (ADR 0003).
    return Settings(env=Environment.TEST, database_url=database_url, s3_bucket="kiln-test")


@pytest.fixture(autouse=True)
def _empty_test_bucket(settings: Settings) -> Iterator[None]:
    """Leave `kiln-test` empty after each test (it is used only by tests)."""
    yield
    client = build_storage(settings)._client
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=settings.s3_bucket):
        for item in page.get("Contents", []):
            client.delete_object(Bucket=settings.s3_bucket, Key=item["Key"])


@pytest.fixture
def real_client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    storage = build_storage(settings)
    try:
        storage.ensure_bucket()
    except StorageUnavailableError as error:
        pytest.fail(
            f"Object storage is not reachable at {settings.s3_endpoint}; run `make up`. ({error})"
        )
    with TestClient(
        create_app(settings, container=build_container(settings, engine=engine, storage=storage))
    ) as client:
        yield client


def _post_file(upload: dict[str, object], content: bytes, content_type: str) -> httpx2.Response:
    fields = upload["fields"]
    assert isinstance(fields, dict)
    url = upload["url"]
    assert isinstance(url, str)
    return httpx2.post(url, data=fields, files={"file": ("upload.bin", content, content_type)})


def test_a_file_posted_with_the_signed_form_completes(real_client: TestClient) -> None:
    created = real_client.post(
        "/api/v1/assets",
        json={
            "name": "Rock",
            "file_name": "rock.png",
            "content_type": "image/png",
            "size_bytes": 64,
        },
    ).json()

    stored = _post_file(created["upload"], b"\x89PNG" + b"0" * 60, "image/png")
    completed = real_client.post(f"/api/v1/asset-versions/{created['version']['id']}/completions")

    assert stored.status_code in {200, 201, 204}
    assert completed.status_code == 200
    assert completed.json()["status"] == "processing"


@pytest.mark.parametrize(("size", "error"), [(65, "EntityTooLarge"), (63, "EntityTooSmall")])
def test_storage_rejects_a_body_of_another_size(
    real_client: TestClient, size: int, error: str
) -> None:
    created = real_client.post(
        "/api/v1/assets",
        json={
            "name": "Rock",
            "file_name": "rock.png",
            "content_type": "image/png",
            "size_bytes": 64,
        },
    ).json()

    stored = _post_file(created["upload"], b"0" * size, "image/png")
    completed = real_client.post(f"/api/v1/asset-versions/{created['version']['id']}/completions")

    assert stored.status_code == 400
    assert error in stored.text
    assert completed.json()["code"] == "UPLOAD_NOT_FOUND"


def test_storage_rejects_another_content_type(real_client: TestClient) -> None:
    created = real_client.post(
        "/api/v1/assets",
        json={
            "name": "Rock",
            "file_name": "rock.png",
            "content_type": "image/png",
            "size_bytes": 4,
        },
    ).json()
    upload = created["upload"]
    tampered = {**upload, "fields": {**upload["fields"], "Content-Type": "text/html"}}

    stored = _post_file(tampered, b"<b/>", "text/html")

    assert stored.status_code == 403


def test_head_reports_size_and_type_and_none_when_absent(settings: Settings) -> None:
    storage = build_storage(settings)
    storage.ensure_bucket()
    key = f"probe/{uuid.uuid4()}.png"
    post = storage.presign_upload(key=key, content_type="image/png", size_bytes=3, ttl_seconds=60)
    httpx2.post(post.url, data=post.fields, files={"file": ("a.png", b"abc", "image/png")})

    found = storage.head(key)

    assert found is not None
    assert (found.size_bytes, found.content_type) == (3, "image/png")
    assert storage.head("probe/missing.png") is None


def test_an_unreachable_endpoint_raises_storage_unavailable(settings: Settings) -> None:
    unreachable = settings.model_copy(update={"s3_endpoint": "http://127.0.0.1:9"})
    storage: S3ObjectStorage = build_storage(unreachable)

    with pytest.raises(StorageUnavailableError):
        storage.ensure_bucket()
    with pytest.raises(StorageUnavailableError):
        storage.head("anything")
    with pytest.raises(StorageUnavailableError):
        storage.promote(source_key="a", target_key="b", etag='"x"')
    with pytest.raises(StorageUnavailableError):
        storage.delete("anything")


def test_reusing_a_signed_form_after_completion_cannot_change_the_file(
    real_client: TestClient, settings: Settings
) -> None:
    created = real_client.post(
        "/api/v1/assets",
        json={
            "name": "Rock",
            "file_name": "rock.png",
            "content_type": "image/png",
            "size_bytes": 4,
        },
    ).json()
    _post_file(created["upload"], b"GOOD", "image/png")
    real_client.post(f"/api/v1/asset-versions/{created['version']['id']}/completions")

    replay = _post_file(created["upload"], b"EVIL", "image/png")
    detail = real_client.get(f"/api/v1/assets/{created['asset']['id']}").json()
    client = build_storage(settings)._client
    final_key = next(
        obj["Key"]
        for obj in client.list_objects_v2(
            Bucket=settings.s3_bucket, Prefix=f"assets/{created['asset']['id']}/"
        )["Contents"]
    )
    content = client.get_object(Bucket=settings.s3_bucket, Key=final_key)["Body"].read()

    assert replay.status_code in {200, 201, 204}  # the staging key accepts it ...
    assert content == b"GOOD"  # ... but the final file never changes
    assert detail["versions"][0]["status"] == "processing"


def test_promotion_with_a_stale_etag_is_refused_by_the_real_server(settings: Settings) -> None:
    storage = build_storage(settings)
    storage.ensure_bucket()
    staging, final = f"uploads/{uuid.uuid4()}", f"assets/{uuid.uuid4()}.png"
    first = storage.presign_upload(
        key=staging, content_type="image/png", size_bytes=4, ttl_seconds=60
    )
    httpx2.post(first.url, data=first.fields, files={"file": ("a.png", b"GOOD", "image/png")})
    checked = storage.head(staging)
    assert checked is not None
    second = storage.presign_upload(
        key=staging, content_type="image/png", size_bytes=4, ttl_seconds=60
    )
    httpx2.post(second.url, data=second.fields, files={"file": ("a.png", b"EVIL", "image/png")})

    promoted = storage.promote(source_key=staging, target_key=final, etag=checked.etag)

    assert promoted is PromotionResult.CHANGED
    assert storage.head(final) is None
    storage.delete(staging)


def _race(client: TestClient, url: str, callers: int) -> list[tuple[int, str]]:
    barrier = threading.Barrier(callers)
    results: list[tuple[int, str]] = []

    def complete() -> None:
        barrier.wait()
        response = client.post(url)
        results.append((response.status_code, response.json().get("status", "")))

    threads = [threading.Thread(target=complete) for _ in range(callers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_concurrent_completions_all_succeed_against_real_storage(real_client: TestClient) -> None:
    outcomes: list[tuple[int, str]] = []
    for _ in range(5):
        created = real_client.post(
            "/api/v1/assets",
            json={
                "name": "Rock",
                "file_name": "rock.png",
                "content_type": "image/png",
                "size_bytes": 4,
            },
        ).json()
        _post_file(created["upload"], b"GOOD", "image/png")
        url = f"/api/v1/asset-versions/{created['version']['id']}/completions"
        outcomes.extend(_race(real_client, url, callers=6))

    assert outcomes == [(200, "processing")] * 30


@pytest.fixture
def blackhole() -> Iterator[str]:
    """A TCP endpoint that accepts connections and never answers (a hung storage server)."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept() -> None:
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                connection, _ = server.accept()
                held.append(connection)
            except TimeoutError:
                continue

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.getsockname()[1]}"
    stop.set()
    thread.join()
    for connection in held:
        connection.close()
    server.close()


def test_a_hung_storage_makes_ready_answer_503_within_seconds(
    settings: Settings, engine: Engine, blackhole: str
) -> None:
    hung = settings.model_copy(update={"s3_endpoint": blackhole})
    container = build_container(hung, engine=engine)

    started = time.monotonic()
    with TestClient(create_app(hung, container=container)) as client:
        response = client.get("/ready")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert response.headers["Retry-After"] == "1"
    assert elapsed < 5  # start-up probe (1 s) + readiness probe (1 s), not the 26 s work budget


def test_upload_download_and_a_signed_get_round_trip(settings: Settings) -> None:
    storage = build_storage(settings)
    storage.ensure_bucket()
    key = f"thumbs/{uuid.uuid4()}.webp"

    storage.upload(key, b"RIFF....WEBP", "image/webp")
    buffer = io.BytesIO()
    storage.download(key, buffer)
    fetched = httpx2.get(storage.presign_download(key, signed_at=datetime.now(UTC), ttl_seconds=60))

    assert buffer.getvalue() == b"RIFF....WEBP"
    assert fetched.status_code == 200
    assert fetched.content == b"RIFF....WEBP"
    assert storage.head(key) is not None
    assert storage.head(key).content_type == "image/webp"  # type: ignore[union-attr]


def test_download_and_upload_report_an_unreachable_storage(settings: Settings) -> None:
    storage = build_storage(settings.model_copy(update={"s3_endpoint": "http://127.0.0.1:9"}))

    with pytest.raises(StorageUnavailableError):
        storage.download("anything", io.BytesIO())
    with pytest.raises(StorageUnavailableError):
        storage.upload("anything", b"x", "image/webp")


def test_a_download_with_a_stale_etag_is_refused_by_the_real_server(settings: Settings) -> None:
    storage = build_storage(settings)
    storage.ensure_bucket()
    key = f"assets/{uuid.uuid4()}.png"
    storage.upload(key, b"first", "image/png")
    stale = storage.head(key)
    assert stale is not None
    storage.upload(key, b"second", "image/png")

    refused = storage.download(key, io.BytesIO(), if_match=stale.etag)
    fresh = storage.head(key)
    assert fresh is not None
    accepted = storage.download(key, io.BytesIO(), if_match=fresh.etag)

    assert (refused, accepted) == (False, True)


def test_listing_finds_old_objects_under_a_prefix_only(settings: Settings) -> None:
    storage = build_storage(settings)
    storage.ensure_bucket()
    prefix = f"uploads/{uuid.uuid4()}/"
    for name in ("a", "b", "c"):
        storage.upload(f"{prefix}{name}", b"x", "application/octet-stream")
    storage.upload(f"thumbs/{uuid.uuid4()}.webp", b"x", "image/webp")
    later = datetime.now(UTC) + timedelta(minutes=1)

    assert sorted(chain.from_iterable(storage.iter_key_pages(prefix, older_than=later))) == [
        f"{prefix}a",
        f"{prefix}b",
        f"{prefix}c",
    ]
    assert (
        list(
            chain.from_iterable(
                storage.iter_key_pages(prefix, older_than=datetime.now(UTC) - timedelta(hours=1))
            )
        )
        == []
    )


def test_a_storage_endpoint_that_refuses_connections_opens_the_circuit(
    database_url: str,
) -> None:
    settings = Settings(
        env=Environment.TEST,
        database_url=database_url,
        s3_endpoint=f"http://127.0.0.1:{_closed_port()}",
        storage_breaker_failures=1,
    )
    storage = guard_storage(build_storage(settings), settings)
    with pytest.raises(StorageUnavailableError) as first:
        storage.head("uploads/x")

    started = time.monotonic()
    with pytest.raises(StorageUnavailableError) as second:
        storage.head("uploads/x")

    assert first.value.cause_code == "EndpointConnectionError"
    assert second.value.cause_code == "CIRCUIT_OPEN"
    assert time.monotonic() - started < 0.05


def test_a_signed_get_is_stable_cacheable_and_expires(settings: Settings) -> None:
    """KILN-27 against real storage: one URL per window, a private cache header, an end."""
    key = f"thumbs/{uuid.uuid4()}.webp"
    build_storage(settings).upload(key, b"RIFF....WEBP", "image/webp")
    window = datetime.now(UTC).replace(second=0, microsecond=0)
    cache = "private, max-age=1500, immutable"

    first = build_storage(settings).presign_download(
        key, signed_at=window, ttl_seconds=1500, cache_control=cache
    )
    second = build_storage(settings).presign_download(
        key, signed_at=window, ttl_seconds=1500, cache_control=cache
    )
    fetched = httpx2.get(first)
    expired = httpx2.get(
        build_storage(settings).presign_download(
            key, signed_at=window - timedelta(hours=1), ttl_seconds=60
        )
    )

    assert first == second
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == cache
    assert expired.status_code == 403


@pytest.mark.parametrize(
    ("name", "tamper"),
    [
        ("another key", lambda url: url.replace(".webp?", "x.webp?")),
        ("public caching", lambda url: url.replace("private", "public")),
        ("a longer life", lambda url: url.replace("X-Amz-Expires=1500", "X-Amz-Expires=9000")),
        ("another response type", lambda url: f"{url}&response-content-type=text%2Fhtml"),
    ],
)
def test_a_tampered_preview_url_is_refused(
    settings: Settings, name: str, tamper: Callable[[str], str]
) -> None:
    """AC5: a URL is one GET of one key with the signed headers, nothing else."""
    key = f"thumbs/{uuid.uuid4()}.webp"
    storage = build_storage(settings)
    storage.upload(key, b"RIFF....WEBP", "image/webp")
    url = storage.presign_download(
        key,
        signed_at=datetime.now(UTC),
        ttl_seconds=1500,
        cache_control="private, max-age=1500, immutable",
    )

    assert httpx2.get(url).status_code == 200
    assert httpx2.get(tamper(url)).status_code == 403, name
    assert httpx2.put(url, content=b"x").status_code == 403


@pytest.mark.parametrize(("age_seconds", "status"), [(1495, 200), (1505, 403)])
def test_a_preview_url_ends_after_its_25_minutes(
    settings: Settings, age_seconds: int, status: int
) -> None:
    """AC4 at the real boundary: signed 1495 s ago still works, 1505 s ago does not."""
    key = f"thumbs/{uuid.uuid4()}.webp"
    storage = build_storage(settings)
    storage.upload(key, b"RIFF....WEBP", "image/webp")
    url = storage.presign_download(
        key, signed_at=datetime.now(UTC) - timedelta(seconds=age_seconds), ttl_seconds=1500
    )

    assert httpx2.get(url).status_code == status
