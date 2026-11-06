"""Adapters for ports that talk to external systems (object storage)."""

from datetime import datetime
from http import HTTPStatus
from typing import IO, TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from kiln_api.enums import PromotionResult
from kiln_api.errors import StorageUnavailableError
from kiln_api.ports import SignedPost, StoredObject

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_MISSING = {str(HTTPStatus.NOT_FOUND.value), "NoSuchKey", "NoSuchBucket", "NotFound"}
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_LIST_PAGE_MAX = 1000  # the S3 maximum for ListObjectsV2
_PRECONDITION_FAILED = {str(HTTPStatus.PRECONDITION_FAILED.value), "PreconditionFailed"}


def _code(error: ClientError) -> str:
    return (error.response or {}).get("Error", {}).get("Code", "")


def _unavailable(error: BotoCoreError | ClientError) -> StorageUnavailableError:
    """Wrap a storage failure, keeping its code (S3 code or botocore class) for the logs."""
    cause = _code(error) if isinstance(error, ClientError) else ""
    return StorageUnavailableError(cause_code=cause or type(error).__name__)


class S3ObjectStorage:
    """`ObjectStorage` over any S3 API (SeaweedFS locally, ADR 0003)."""

    def __init__(
        self, client: "S3Client", bucket: str, probe_client: "S3Client | None" = None
    ) -> None:
        """Use `client` for work and a fast `probe_client` (1 s, one attempt) for readiness."""
        self._client = client
        self._probe = probe_client or client
        self._bucket = bucket

    def ensure_bucket(self) -> None:
        """Create the bucket when a fast `HeadBucket` (probe client) says it does not exist."""
        try:
            self._probe.head_bucket(Bucket=self._bucket)
        except ClientError as error:
            if _code(error) not in _MISSING:
                raise _unavailable(error) from error
            self._create_bucket()
        except BotoCoreError as error:
            raise _unavailable(error) from error

    def _create_bucket(self) -> None:
        try:
            self._client.create_bucket(Bucket=self._bucket)
        except (BotoCoreError, ClientError) as error:
            raise _unavailable(error) from error

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
            raise _unavailable(error) from error
        except BotoCoreError as error:
            raise _unavailable(error) from error
        return StoredObject(
            size_bytes=response["ContentLength"],
            content_type=response.get("ContentType", ""),
            etag=response["ETag"],
        )

    def ping(self) -> None:
        """`HeadBucket` with the probe client; never creates anything."""
        try:
            self._probe.head_bucket(Bucket=self._bucket)
        except (BotoCoreError, ClientError) as error:
            raise _unavailable(error) from error

    def promote(self, *, source_key: str, target_key: str, etag: str) -> PromotionResult:
        """Server-side conditional copy; 412 when the source changed, 404 when it is gone."""
        try:
            self._client.copy_object(
                Bucket=self._bucket,
                Key=target_key,
                CopySource={"Bucket": self._bucket, "Key": source_key},
                CopySourceIfMatch=etag,
            )
        except ClientError as error:
            if _code(error) in _PRECONDITION_FAILED:
                return PromotionResult.CHANGED
            if _code(error) in _MISSING:
                return PromotionResult.SOURCE_GONE
            raise _unavailable(error) from error
        except BotoCoreError as error:
            raise _unavailable(error) from error
        return PromotionResult.PROMOTED

    def delete(self, key: str) -> None:
        """Delete `key` (S3 deletes are idempotent)."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            raise _unavailable(error) from error

    def list_keys(self, prefix: str, *, older_than: datetime, limit: int) -> list[str]:
        """Page through `ListObjectsV2` under `prefix`, stopping once `limit` old keys are found."""
        keys: list[str] = []
        try:
            pages = self._client.get_paginator("list_objects_v2").paginate(
                Bucket=self._bucket,
                Prefix=prefix,
                PaginationConfig={"PageSize": min(limit, _LIST_PAGE_MAX)},
            )
            for page in pages:
                for item in page.get("Contents", []):
                    if item["LastModified"] < older_than:
                        keys.append(item["Key"])
                        if len(keys) >= limit:
                            return keys
        except (BotoCoreError, ClientError) as error:
            raise _unavailable(error) from error
        return keys

    def download(self, key: str, into: IO[bytes], *, if_match: str | None = None) -> bool:
        """Stream with the work client; with `if_match`, refuse an object that changed (412)."""
        # download_fileobj does not accept IfMatch, so stream GetObject ourselves.
        try:
            response = (
                self._client.get_object(Bucket=self._bucket, Key=key)
                if if_match is None
                else self._client.get_object(Bucket=self._bucket, Key=key, IfMatch=if_match)
            )
            body = response["Body"]
            for chunk in body.iter_chunks(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                into.write(chunk)
        except ClientError as error:
            if _code(error) in _PRECONDITION_FAILED:
                return False
            raise _unavailable(error) from error
        except BotoCoreError as error:
            raise _unavailable(error) from error
        return True

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        """Put a Kiln-generated object."""
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except (BotoCoreError, ClientError) as error:
            raise _unavailable(error) from error

    def presign_download(self, key: str, ttl_seconds: int) -> str:
        """Sign a GET locally."""
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=ttl_seconds
        )
