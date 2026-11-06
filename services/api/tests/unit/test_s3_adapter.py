import base64
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import islice

import boto3
import pytest
from botocore.exceptions import ReadTimeoutError
from botocore.stub import Stubber

from kiln_api.adapters import S3ObjectStorage
from kiln_api.enums import PromotionResult
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

    result = storage.promote(source_key="uploads/a", target_key="assets/a", etag='"checked-etag"')

    assert result is PromotionResult.PROMOTED


def test_a_changed_source_makes_promotion_return_changed(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error(
        "copy_object", service_error_code="PreconditionFailed", http_status_code=412
    )

    result = storage.promote(source_key="uploads/a", target_key="assets/a", etag='"x"')

    assert result is PromotionResult.CHANGED


def test_a_source_deleted_by_a_concurrent_completion_is_reported_as_gone(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("copy_object", service_error_code="NoSuchKey", http_status_code=404)

    result = storage.promote(source_key="uploads/a", target_key="assets/a", etag='"x"')

    assert result is PromotionResult.SOURCE_GONE


def test_ping_uses_head_bucket_and_maps_failures(stubbed: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_response("head_bucket", {}, {"Bucket": "kiln-assets"})
    stubber.add_client_error("head_bucket", service_error_code="404", http_status_code=404)

    storage.ping()
    with pytest.raises(StorageUnavailableError):
        storage.ping()


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


class _HangingClient:
    """Stands in for a boto3 client whose calls time out (botocore sets `response=None`)."""

    def head_object(self, **_: object) -> None:
        raise ReadTimeoutError(endpoint_url="http://storage.test")


def test_a_read_timeout_becomes_unavailable_with_its_class_as_the_cause() -> None:
    storage = S3ObjectStorage(_HangingClient(), "kiln-assets")  # type: ignore[arg-type]

    with pytest.raises(StorageUnavailableError) as raised:
        storage.head("uploads/a")

    assert raised.value.cause_code == "ReadTimeoutError"


def test_an_s3_error_keeps_its_code_as_the_cause(stubbed: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("head_object", service_error_code="SlowDown", http_status_code=503)

    with pytest.raises(StorageUnavailableError) as raised:
        storage.head("uploads/a")

    assert raised.value.cause_code == "SlowDown"


def test_a_download_error_other_than_412_is_reported_as_unavailable(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("get_object", service_error_code="InternalError", http_status_code=500)

    with pytest.raises(StorageUnavailableError):
        storage.download("assets/a.png", io.BytesIO(), if_match='"x"')


def test_listing_yields_only_old_keys_page_by_page(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    cutoff = datetime(2026, 11, 5, tzinfo=UTC)
    old, young = cutoff - timedelta(seconds=1), cutoff
    stubber.add_response(
        "list_objects_v2",
        {
            "Contents": [
                {"Key": "uploads/a/1", "LastModified": old},
                {"Key": "uploads/a/2", "LastModified": young},
                {"Key": "uploads/a/3", "LastModified": old},
            ],
            "IsTruncated": True,
            "NextContinuationToken": "t",
        },
        {"Bucket": "kiln-assets", "Prefix": "uploads/", "MaxKeys": 1000},
    )
    stubber.add_response(
        "list_objects_v2",
        {
            "Contents": [
                {"Key": "uploads/b/4", "LastModified": old},
                {"Key": "uploads/b/5", "LastModified": old},
            ],
            "IsTruncated": False,
        },
        {"Bucket": "kiln-assets", "Prefix": "uploads/", "MaxKeys": 1000, "ContinuationToken": "t"},
    )

    # Lazy: the second page is fetched only when read; young keys are skipped; the caller stops.
    assert list(islice(storage.iter_keys("uploads/", older_than=cutoff), 3)) == [
        "uploads/a/1",
        "uploads/a/3",
        "uploads/b/4",
    ]


def test_listing_errors_are_reported_as_unavailable(
    stubbed: tuple[S3ObjectStorage, Stubber],
) -> None:
    storage, stubber = stubbed
    stubber.add_client_error("list_objects_v2", service_error_code="SlowDown", http_status_code=503)

    with pytest.raises(StorageUnavailableError) as raised:
        list(storage.iter_keys("uploads/", older_than=datetime.now(UTC)))
    assert raised.value.cause_code == "SlowDown"
