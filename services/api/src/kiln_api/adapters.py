"""Adapters for ports that talk to external systems (object storage)."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from kiln_api.errors import StorageUnavailableError
from kiln_api.ports import SignedPost, StoredObject

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_MISSING = {str(HTTPStatus.NOT_FOUND.value), "NoSuchKey", "NoSuchBucket", "NotFound"}


def _is_missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code", "") in _MISSING


class S3ObjectStorage:
    """`ObjectStorage` over any S3 API (SeaweedFS locally, ADR 0003)."""

    def __init__(self, client: "S3Client", bucket: str) -> None:
        """Use `client` (configured with timeouts and retries) for `bucket`."""
        self._client = client
        self._bucket = bucket

    def ensure_bucket(self) -> None:
        """Create the bucket when `HeadBucket` says it does not exist."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as error:
            if not _is_missing(error):
                raise StorageUnavailableError from error
            self._create_bucket()
        except BotoCoreError as error:
            raise StorageUnavailableError from error

    def _create_bucket(self) -> None:
        try:
            self._client.create_bucket(Bucket=self._bucket)
        except (BotoCoreError, ClientError) as error:
            raise StorageUnavailableError from error

    def presign_upload(
        self, *, key: str, content_type: str, size_bytes: int, ttl_seconds: int
    ) -> SignedPost:
        """Sign locally; no network call is made (ADR 0004)."""
        post = self._client.generate_presigned_post(
            Bucket=self._bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", size_bytes, size_bytes],
            ],
            ExpiresIn=ttl_seconds,
        )
        return SignedPost(
            url=post["url"], fields={name: str(value) for name, value in post["fields"].items()}
        )

    def head(self, key: str) -> StoredObject | None:
        """Return size and type of the object, None when it is absent."""
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if _is_missing(error):
                return None
            raise StorageUnavailableError from error
        except BotoCoreError as error:
            raise StorageUnavailableError from error
        return StoredObject(
            size_bytes=response["ContentLength"], content_type=response.get("ContentType", "")
        )
