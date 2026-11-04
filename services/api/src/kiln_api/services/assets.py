"""Asset use cases: create, add a version, confirm an upload, read."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from kiln_api.constants import UPLOAD_URL_TTL_SECONDS
from kiln_api.domain.assets import (
    Asset,
    AssetVersion,
    IdFactory,
    UploadSpec,
    new_asset,
    new_version,
    transition,
    upload_key,
)
from kiln_api.enums import VersionStatus
from kiln_api.errors import InvalidStatusTransitionError, UploadMismatchError, UploadNotFoundError
from kiln_api.ports import AssetRepository, Clock, ObjectStorage, Page, StoredObject


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    """A signed upload form and when it stops working."""

    url: str
    fields: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class PendingUpload:
    """A version waiting for its file, with the signed form to upload it."""

    asset: Asset
    version: AssetVersion
    upload: PresignedUpload


@dataclass(frozen=True, slots=True)
class AssetDetail:
    """An asset with its versions by number."""

    asset: Asset
    versions: list[AssetVersion]


class AssetService:
    """Coordinates the repository, object storage and the clock."""

    def __init__(
        self,
        repository: AssetRepository,
        storage: ObjectStorage,
        clock: Clock,
        new_id: IdFactory,
    ) -> None:
        """Receive every collaborator through its port."""
        self._repository = repository
        self._storage = storage
        self._clock = clock
        self._new_id = new_id

    def create(self, name: str, spec: UploadSpec) -> PendingUpload:
        """Store a new asset with version 1 and sign its upload."""
        asset, version = new_asset(name, spec, now=self._clock.now(), new_id=self._new_id)
        self._repository.add(asset, version)
        return PendingUpload(asset=asset, version=version, upload=self._sign(version))

    def add_version(self, asset_id: UUID, spec: UploadSpec) -> PendingUpload:
        """Store the next version of an asset and sign its upload."""
        now = self._clock.now()
        version = self._repository.add_next_version(
            asset_id,
            lambda asset, number: new_version(asset, number, spec, now=now, new_id=self._new_id),
        )
        asset = self._repository.get(asset_id)
        return PendingUpload(asset=asset, version=version, upload=self._sign(version))

    def complete_upload(self, version_id: UUID) -> AssetVersion:
        """Check the stored object against the declaration and start processing.

        The file is copied from the staging key to the final key only if it is byte-for-byte
        the object that was checked (ETag), so a signed form reused later cannot change it.
        Idempotent: a version that already left `pending_upload` is returned unchanged, and a
        retry after a partial failure resumes where it stopped.
        """
        version = self._repository.get_version(version_id)
        if version.status is not VersionStatus.PENDING_UPLOAD:
            return version
        staging = upload_key(version)
        stored = self._storage.head(staging)
        if stored is not None:
            self._check_declared(version, stored)
            if not self._storage.promote(
                source_key=staging, target_key=version.object_key, etag=stored.etag
            ):
                raise UploadMismatchError  # replaced between the check and the copy
            self._storage.delete(staging)
        else:
            promoted = self._storage.head(version.object_key)
            if promoted is None:
                raise UploadNotFoundError
            self._check_declared(version, promoted)  # resumed after an earlier promotion
        processing = transition(version, VersionStatus.PROCESSING, now=self._clock.now())
        try:
            self._repository.save_version(processing, expected=VersionStatus.PENDING_UPLOAD)
        except InvalidStatusTransitionError:
            return self._repository.get_version(version_id)  # a concurrent completion won
        return processing

    def get(self, asset_id: UUID) -> AssetDetail:
        """Return an asset with its versions."""
        asset = self._repository.get(asset_id)
        return AssetDetail(asset=asset, versions=self._repository.versions_of(asset_id))

    def get_version(self, version_id: UUID) -> AssetVersion:
        """Return one version."""
        return self._repository.get_version(version_id)

    def list(self, *, cursor: str | None, limit: int) -> Page[Asset]:
        """Return assets newest first."""
        return self._repository.list_page(cursor=cursor, limit=limit)

    @staticmethod
    def _check_declared(version: AssetVersion, stored: StoredObject) -> None:
        if stored.size_bytes != version.size_bytes or stored.content_type != version.content_type:
            raise UploadMismatchError

    def _sign(self, version: AssetVersion) -> PresignedUpload:
        expires_at = self._clock.now() + timedelta(seconds=UPLOAD_URL_TTL_SECONDS)
        post = self._storage.presign_upload(
            key=upload_key(version),
            content_type=version.content_type,
            size_bytes=version.size_bytes,
            ttl_seconds=UPLOAD_URL_TTL_SECONDS,
        )
        return PresignedUpload(url=post.url, fields=post.fields, expires_at=expires_at)
