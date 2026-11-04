import base64
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from botocore.stub import Stubber

from kiln_api.adapters import S3ObjectStorage
from kiln_api.errors import StorageUnavailableError


@pytest.fixture
def stubbed() -> Iterator[tuple[S3ObjectStorage, Stubber]]:
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        endpoint_url="http://storage.test",
        aws_access_key_id="k",
        aws_secret_access_key="s",
    )
    with Stubber(client) as stubber:
        yield S3ObjectStorage(client, "kiln-assets"), stubber
        stubber.assert_no_pending_responses()


def test_an_existing_bucket_is_left_alone(stubbed: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_response("head_bucket", {}, {"Bucket": "kiln-assets"})

    storage.ensure_bucket()


def test_a_missing_bucket_is_created(stubbed: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
    stubber.add_response("create_bucket", {}, {"Bucket": "kiln-assets"})

    storage.ensure_bucket()


def test_a_forbidden_bucket_is_reported_as_unavailable(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("head_bucket", service_error_code="403", http_status_code=403)

    with pytest.raises(StorageUnavailableError):
        storage.ensure_bucket()


def test_a_failed_bucket_creation_is_reported_as_unavailable(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("head_bucket", service_error_code="NoSuchBucket", http_status_code=404)
    stubber.add_client_error(
        "create_bucket", service_error_code="AccessDenied", http_status_code=403
    )

    with pytest.raises(StorageUnavailableError):
        storage.ensure_bucket()


def test_promotion_copies_only_if_the_source_etag_still_matches(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_response(
        "copy_object",
        {},
        {
            "Bucket": "kiln-assets",
            "Key": "assets/a",
            "CopySource": {"Bucket": "kiln-assets", "Key": "uploads/a"},
            "CopySourceIfMatch": '"checked-etag"',
        },
    )

    assert storage.promote(source_key="uploads/a", target_key="assets/a", etag='"checked-etag"')


def test_a_changed_source_makes_promotion_return_false(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error(
        "copy_object", service_error_code="PreconditionFailed", http_status_code=412
    )

    assert storage.promote(source_key="uploads/a", target_key="assets/a", etag='"x"') is False


def test_other_copy_errors_are_reported_as_unavailable(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error(
        "copy_object", service_error_code="InternalError", http_status_code=500
    )

    with pytest.raises(StorageUnavailableError):
        storage.promote(source_key="uploads/a", target_key="assets/a", etag='"x"')


def test_delete_errors_are_reported_as_unavailable(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error(
        "delete_object", service_error_code="InternalError", http_status_code=500
    )

    with pytest.raises(StorageUnavailableError):
        storage.delete("uploads/a")


def test_a_server_error_on_head_object_is_reported_as_unavailable(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error(
        "head_object", service_error_code="InternalError", http_status_code=500
    )

    with pytest.raises(StorageUnavailableError):
        storage.head("assets/a.png")


def test_a_signed_post_pins_key_type_and_exact_size(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, _ = stubbed

    post = storage.presign_upload(
        key="assets/a/v1/b.png", content_type="image/png", size_bytes=42, ttl_seconds=900
    )

    assert post.url.startswith("http://storage.test")
    assert post.fields["key"] == "assets/a/v1/b.png"
    assert post.fields["Content-Type"] == "image/png"
    assert "policy" in post.fields
    policy = json.loads(base64.b64decode(post.fields["policy"]))
    assert ["content-length-range", 42, 42] in policy["conditions"]
    assert {"Content-Type": "image/png"} in policy["conditions"]
    expiration = datetime.fromisoformat(policy["expiration"].replace("Z", "+00:00"))
    assert timedelta(minutes=14) < expiration - datetime.now(UTC) <= timedelta(minutes=15)
