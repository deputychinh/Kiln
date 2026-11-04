"""Against the real SeaweedFS from `make up` (ADR 0003): the signed POST policy and HEAD."""

import uuid
from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from kiln_api.adapters import S3ObjectStorage
from kiln_api.config import Settings
from kiln_api.container import build_container, build_storage
from kiln_api.enums import Environment
from kiln_api.errors import StorageUnavailableError
from kiln_api.main import create_app


@pytest.fixture
def settings(database_url: str) -> Settings:
    # One shared bucket: every SeaweedFS bucket reserves its own volumes (ADR 0003).
    return Settings(env=Environment.TEST, database_url=database_url, s3_bucket="kiln-test")


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

    assert promoted is False
    assert storage.head(final) is None
    storage.delete(staging)
