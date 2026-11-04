"""Adapters for ports that talk to external systems (object storage)."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from kiln_api.errors import StorageUnavailableError
from kiln_api.ports import SignedPost, StoredObject

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_MISSING = {str(HTTPStatus.NOT_FOUND.value), "NoSuchKey", "NoSuchBucket", "NotFound"}
_PRECONDITION_FAILED = {str(HTTPStatus.PRECONDITION_FAILED.value), "PreconditionFailed"}


def _code(error: ClientError) -> str:
    return error.response.get("Error", {}).get("Code", "")


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
            if _code(error) not in _MISSING:
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
            if _code(error) in _MISSING:
                return None
            raise StorageUnavailableError from error
        except BotoCoreError as error:
            raise StorageUnavailableError from error
        return StoredObject(
            size_bytes=response["ContentLength"],
            content_type=response.get("ContentType", ""),
            etag=response["ETag"],
        )

    def promote(self, *, source_key: str, target_key: str, etag: str) -> bool:
        """Server-side conditional copy; S3 answers 412 when the source changed."""
        try:
            self._client.copy_object(
                Bucket=self._bucket,
                Key=target_key,
                CopySource={"Bucket": self._bucket, "Key": source_key},
                CopySourceIfMatch=etag,
            )
        except ClientError as error:
            if _code(error) in _PRECONDITION_FAILED:
                return False
            raise StorageUnavailableError from error
        except BotoCoreError as error:
            raise StorageUnavailableError from error
        return True

    def delete(self, key: str) -> None:
        """Delete `key` (S3 deletes are idempotent)."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            raise StorageUnavailableError from error
