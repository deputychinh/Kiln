"""Abstract ports the services depend on; adapters live in `repositories/` and `adapters/`."""

from collections.abc import Callable, Iterator, Sequence
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

    def download(self, key: str, into: IO[bytes], *, if_match: str | None = None) -> bool:
        """Stream the object into a file object; False when it no longer matches `if_match`."""
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

    def iter_key_pages(self, prefix: str, *, older_than: datetime) -> Iterator[list[str]]:
        """Pages of keys under `prefix` last modified before `older_than`.

        Each step fetches exactly one listing page (one network call); a page may be empty.
        """
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

    def versions_by_id(self, version_ids: Sequence[UUID]) -> dict[UUID, AssetVersion]:
        """The versions among `version_ids` that exist, in one query."""
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
    """Background work stored next to the data it is about.

    `now=None` means the database clock; tests pass explicit times. State changes after a claim
    return False when the claim no longer owns the job (its lease expired and it was re-claimed).
    """

    def enqueue(self, job: Job) -> None:
        """Store a new job."""
        ...

    def claim(
        self, *, lease: timedelta, max_attempts: int, now: datetime | None = None
    ) -> Job | None:
        """Take the next runnable job that still has attempts left, or return None."""
        ...

    def exhausted_jobs(self, *, max_attempts: int, now: datetime | None = None) -> list[Job]:
        """Expired running jobs with no attempts left, to bury them."""
        ...

    def extend(self, job: Job, *, lease: timedelta, now: datetime | None = None) -> bool:
        """Push the claimed job's still-valid lease to `now + lease`; False otherwise."""
        ...

    def finish(self, job: Job, *, now: datetime | None = None) -> bool:
        """Mark a claimed job done."""
        ...

    def retry(self, job: Job, *, delay: timedelta, error: str, now: datetime | None = None) -> bool:
        """Requeue a claimed job after `delay`."""
        ...

    def bury(self, job: Job, *, error: str, now: datetime | None = None) -> bool:
        """Mark a claimed job dead."""
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


class MaintenanceStore(Protocol):
    """Run lease and stale-upload query for scheduled maintenance (KILN-22)."""

    def try_start(self, task: str, *, every: timedelta, now: datetime | None = None) -> bool:
        """Take the run of `task` if none started within `every`."""
        ...

    def stale_pending_versions(
        self, *, older_than: timedelta, limit: int, now: datetime | None = None
    ) -> list[UUID]:
        """Ids of versions still waiting for their upload after `older_than`, oldest first."""
        ...
