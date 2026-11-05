"""Abstract ports the services depend on; adapters live in `repositories/` and `adapters/`."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import IO, Protocol
from uuid import UUID

from kiln_api.domain.assets import Asset, AssetVersion
from kiln_api.domain.jobs import Job
from kiln_api.enums import PromotionResult, VersionStatus


@dataclass(frozen=True, slots=True)
class Page[T]:
    """One page of a newest-first list; `next_cursor` is None on the last page."""

    items: tuple[T, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class SignedPost:
    """Where and how a client posts one file: form `fields` plus the file, to `url`."""

    url: str
    fields: dict[str, str]


@dataclass(frozen=True, slots=True)
class StoredObject:
    """What storage reports about an uploaded object."""

    size_bytes: int
    content_type: str
    etag: str


class ObjectStorage(Protocol):
    """S3-compatible object storage; every failure surfaces as `StorageUnavailableError`."""

    def ensure_bucket(self) -> None:
        """Create the bucket if it is missing; doubles as the readiness probe."""
        ...

    def presign_upload(
        self, *, key: str, content_type: str, size_bytes: int, ttl_seconds: int
    ) -> SignedPost:
        """Sign a POST policy pinning the key, the content type and the exact size."""
        ...

    def head(self, key: str) -> StoredObject | None:
        """Describe the object at `key`, or return None when it does not exist."""
        ...

    def promote(self, *, source_key: str, target_key: str, etag: str) -> PromotionResult:
        """Copy `source_key` to `target_key` only if its ETag is still `etag`."""
        ...

    def ping(self) -> None:
        """Fast readiness check (about 1 s, one attempt); raise `StorageUnavailableError`."""
        ...

    def download(self, key: str, into: IO[bytes]) -> None:
        """Stream the object at `key` into a file object."""
        ...

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        """Write a small object (thumbnails) written by Kiln itself."""
        ...

    def presign_download(self, key: str, ttl_seconds: int) -> str:
        """A time-limited GET URL; signed locally, no network call."""
        ...

    def delete(self, key: str) -> None:
        """Remove `key`; a missing key is not an error."""
        ...


class Clock(Protocol):
    """Source of the current time (UTC)."""

    def now(self) -> datetime:
        """Return the current time with a timezone."""
        ...


class AssetRepository(Protocol):
    """Persistence of assets and their versions."""

    def add(self, asset: Asset, first_version: AssetVersion) -> None:
        """Store a new asset with its first version atomically."""
        ...

    def get(self, asset_id: UUID) -> Asset:
        """Return an asset or raise `AssetNotFoundError`."""
        ...

    def list_page(self, *, cursor: str | None, limit: int) -> Page[Asset]:
        """Return assets newest first after `cursor`; `limit` is clamped to 1 to 100."""
        ...

    def add_next_version(
        self, asset_id: UUID, build: Callable[[Asset, int], AssetVersion]
    ) -> AssetVersion:
        """Lock the asset, build the version with the next number and store it."""
        ...

    def get_version(self, version_id: UUID) -> AssetVersion:
        """Return a version or raise `AssetVersionNotFoundError`."""
        ...

    def versions_of(self, asset_id: UUID) -> list[AssetVersion]:
        """Return an asset's versions by number, at most `MAX_VERSIONS_PER_READ` (500)."""
        ...

    def save_version(self, version: AssetVersion, *, expected: VersionStatus) -> None:
        """Persist a status change if the stored status is still `expected`.

        Raises `AssetVersionNotFoundError`, or `InvalidStatusTransitionError` when another
        writer changed the status first.
        """
        ...

    def promote_cover(self, version: AssetVersion) -> None:
        """Make a ready `version` the asset's cover unless a newer version already is."""
        ...


@dataclass(frozen=True, slots=True)
class IdempotentResult:
    """What a completed idempotent request created."""

    asset_id: UUID | None
    version_id: UUID | None


class IdempotencyStore(Protocol):
    """Idempotency keys stored in the caller's transaction."""

    def claim(
        self, *, key: str, operation: str, request_hash: bytes, now: datetime
    ) -> IdempotentResult | None:
        """Claim `key` (None) or return the earlier result; raise on reuse or a long wait."""
        ...

    def complete(self, *, key: str, asset_id: UUID, version_id: UUID) -> None:
        """Record the created ids for `key`."""
        ...


class JobQueue(Protocol):
    """Background work stored next to the data it is about."""

    def enqueue(self, job: Job) -> None:
        """Store a new job."""
        ...

    def claim(self, *, now: datetime, lease: timedelta) -> Job | None:
        """Take the next runnable job with a lease, or return None."""
        ...

    def finish(self, job_id: UUID, *, now: datetime) -> None:
        """Mark a job done."""
        ...

    def retry(self, job_id: UUID, *, run_after: datetime, error: str, now: datetime) -> None:
        """Requeue a job for a later attempt."""
        ...

    def bury(self, job_id: UUID, *, error: str, now: datetime) -> None:
        """Mark a job dead."""
        ...


class Transaction(Protocol):
    """Repositories that share one database transaction."""

    @property
    def assets(self) -> AssetRepository:
        """Assets and versions in this transaction."""
        ...

    @property
    def idempotency(self) -> IdempotencyStore:
        """Idempotency keys in this transaction."""
        ...

    @property
    def jobs(self) -> JobQueue:
        """Jobs in this transaction (outbox)."""
        ...


class UnitOfWork(Protocol):
    """Opens a transaction; commits when the block ends, rolls back on an exception."""

    def __call__(self) -> AbstractContextManager[Transaction]:
        """Start a transaction."""
        ...
