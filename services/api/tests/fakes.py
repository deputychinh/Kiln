"""Fakes for ports that leave the process (storage, clock)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import IO

from kiln_api.enums import PromotionResult
from kiln_api.errors import StorageUnavailableError
from kiln_api.ports import SignedPost, StoredObject


class FakeStorage:
    """In-memory object storage; `put` simulates a client upload."""

    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.blobs: dict[str, bytes] = {}
        self.signed: list[dict[str, object]] = []
        self.available = True
        self.bucket_ready = False
        self.on_head: Callable[[], None] | None = None
        self.promote_succeeds = True
        self.force_source_gone = False
        self.ensure_calls = 0
        self.delete_available = True
        self.modified: dict[str, datetime] = {}
        self.list_available = True

    def ensure_bucket(self) -> None:
        self.ensure_calls += 1
        self._check()
        self.bucket_ready = True

    def presign_upload(
        self, *, key: str, content_type: str, size_bytes: int, ttl_seconds: int
    ) -> SignedPost:
        self.signed.append(
            {"key": key, "content_type": content_type, "size": size_bytes, "ttl": ttl_seconds}
        )
        return SignedPost(
            url="http://storage.test/kiln-assets",
            fields={"key": key, "Content-Type": content_type, "policy": "signed"},
        )

    def head(self, key: str) -> StoredObject | None:
        self._check()
        if self.on_head is not None:
            self.on_head()  # lets a test interleave another request (race simulation)
        return self.objects.get(key)

    def promote(self, *, source_key: str, target_key: str, etag: str) -> PromotionResult:
        self._check()
        source = self.objects.get(source_key)
        if source is None or self.force_source_gone:
            return PromotionResult.SOURCE_GONE
        if not self.promote_succeeds or source.etag != etag:
            return PromotionResult.CHANGED
        self.objects[target_key] = source
        if source_key in self.blobs:
            self.blobs[target_key] = self.blobs[source_key]
        return PromotionResult.PROMOTED

    def ping(self) -> None:
        self._check()

    def delete(self, key: str) -> None:
        self._check()
        if not self.delete_available:
            raise StorageUnavailableError
        self.objects.pop(key, None)
        self.blobs.pop(key, None)

    def put(
        self,
        key: str,
        size_bytes: int,
        content_type: str,
        data: bytes | None = None,
        *,
        modified_at: datetime | None = None,
    ) -> None:
        etag = f'"{len(self.objects)}-{size_bytes}"'
        self.objects[key] = StoredObject(
            size_bytes=size_bytes, content_type=content_type, etag=etag
        )
        if data is not None:
            self.blobs[key] = data
        self.modified[key] = modified_at or datetime.now(UTC)

    def download(self, key: str, into: IO[bytes], *, if_match: str | None = None) -> bool:
        self._check()
        if if_match is not None and self.objects[key].etag != if_match:
            return False
        into.write(self.blobs[key])
        return True

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        self._check()
        self.put(key, len(data), content_type, data)

    def list_keys(self, prefix: str, *, older_than: datetime, limit: int) -> list[str]:
        self._check()
        if not self.list_available:
            raise StorageUnavailableError
        old = sorted(
            key
            for key in self.objects
            if key.startswith(prefix) and self.modified.get(key, older_than) < older_than
        )
        return old[:limit]

    def presign_download(self, key: str, ttl_seconds: int) -> str:
        return f"http://storage.test/kiln-assets/{key}?ttl={ttl_seconds}"

    def _check(self) -> None:
        if not self.available:
            raise StorageUnavailableError


class FixedClock:
    """A clock that only moves when told to."""

    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 11, 4, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
