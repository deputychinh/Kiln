"""Fakes for ports that leave the process (storage, clock)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from kiln_api.enums import PromotionResult
from kiln_api.errors import StorageUnavailableError
from kiln_api.ports import SignedPost, StoredObject


class FakeStorage:
    """In-memory object storage; `put` simulates a client upload."""

    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.signed: list[dict[str, object]] = []
        self.available = True
        self.bucket_ready = False
        self.on_head: Callable[[], None] | None = None
        self.promote_succeeds = True
        self.delete_available = True

    def ensure_bucket(self) -> None:
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
        if source is None:
            return PromotionResult.SOURCE_GONE
        if not self.promote_succeeds or source.etag != etag:
            return PromotionResult.CHANGED
        self.objects[target_key] = source
        return PromotionResult.PROMOTED

    def ping(self) -> None:
        self._check()

    def delete(self, key: str) -> None:
        self._check()
        if not self.delete_available:
            raise StorageUnavailableError
        self.objects.pop(key, None)

    def put(self, key: str, size_bytes: int, content_type: str) -> None:
        etag = f'"{len(self.objects)}-{size_bytes}"'
        self.objects[key] = StoredObject(
            size_bytes=size_bytes, content_type=content_type, etag=etag
        )

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
