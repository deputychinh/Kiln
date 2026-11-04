"""Abstract ports the services depend on; adapters live in `repositories/` and `adapters/`."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from kiln_api.domain.assets import Asset, AssetVersion
from kiln_api.enums import VersionStatus


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
