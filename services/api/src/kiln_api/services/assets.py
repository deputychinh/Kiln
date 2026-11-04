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
from kiln_api.domain.idempotency import request_fingerprint
from kiln_api.enums import PromotionResult, VersionStatus
from kiln_api.errors import (
    IdempotencyKeyInUseError,
    InvalidStatusTransitionError,
    UploadMismatchError,
    UploadNotFoundError,
)
from kiln_api.ports import (
    AssetRepository,
    Clock,
    IdempotentResult,
    ObjectStorage,
    Page,
    StoredObject,
    Transaction,
    UnitOfWork,
)


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
    upload: PresignedUpload | None  # None when a replayed version no longer takes an upload
    replayed: bool = False


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
        unit_of_work: UnitOfWork,
    ) -> None:
        """Receive every collaborator through its port."""
        self._repository = repository
        self._storage = storage
        self._clock = clock
        self._new_id = new_id
        self._unit_of_work = unit_of_work

    def create(
        self, name: str, spec: UploadSpec, *, idempotency_key: str | None = None
    ) -> PendingUpload:
        """Store a new asset with version 1 and sign its upload.

        With an idempotency key, a repeat within the window replays the first result.
        """
        payload = {"name": name, **_payload(spec)}
        with self._unit_of_work() as tx:
            replay = self._claim(tx, idempotency_key, "create_asset", payload)
            if replay is not None:
                return self._replayed(tx, replay)
            asset, version = new_asset(name, spec, now=self._clock.now(), new_id=self._new_id)
            tx.assets.add(asset, version)
            self._complete(tx, idempotency_key, version)
        return PendingUpload(asset=asset, version=version, upload=self._sign(version))

    def add_version(
        self, asset_id: UUID, spec: UploadSpec, *, idempotency_key: str | None = None
    ) -> PendingUpload:
        """Store the next version of an asset and sign its upload (idempotent with a key)."""
        now = self._clock.now()
        with self._unit_of_work() as tx:
            replay = self._claim(tx, idempotency_key, f"add_version:{asset_id}", _payload(spec))
            if replay is not None:
                return self._replayed(tx, replay)
            version = tx.assets.add_next_version(
                asset_id,
                lambda asset, number: new_version(
                    asset, number, spec, now=now, new_id=self._new_id
                ),
            )
            asset = tx.assets.get(asset_id)
            self._complete(tx, idempotency_key, version)
        return PendingUpload(asset=asset, version=version, upload=self._sign(version))

    def _claim(
        self, tx: Transaction, key: str | None, operation: str, payload: dict[str, object]
    ) -> IdempotentResult | None:
        if key is None:
            return None
        return tx.idempotency.claim(
            key=key,
            operation=operation,
            request_hash=request_fingerprint(operation, payload),
            now=self._clock.now(),
        )

    @staticmethod
    def _complete(tx: Transaction, key: str | None, version: AssetVersion) -> None:
        if key is not None:
            tx.idempotency.complete(key=key, asset_id=version.asset_id, version_id=version.id)

    def _replayed(self, tx: Transaction, replay: IdempotentResult) -> PendingUpload:
        if replay.asset_id is None or replay.version_id is None:
            raise IdempotencyKeyInUseError  # cannot happen after commit; never replay half a result
        version = tx.assets.get_version(replay.version_id)
        upload = self._sign(version) if version.status is VersionStatus.PENDING_UPLOAD else None
        return PendingUpload(
            asset=tx.assets.get(replay.asset_id), version=version, upload=upload, replayed=True
        )

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
        result = PromotionResult.SOURCE_GONE
        if stored is not None:
            self._check_declared(version, stored)
            result = self._storage.promote(
                source_key=staging, target_key=version.object_key, etag=stored.etag
            )
            if result is PromotionResult.CHANGED:
                raise UploadMismatchError  # replaced between the check and the copy
        if result is PromotionResult.PROMOTED:
            self._storage.delete(staging)
        else:
            # No staging object: an earlier or concurrent completion already promoted it.
            promoted = self._storage.head(version.object_key)
            if promoted is None:
                raise UploadNotFoundError
            self._check_declared(version, promoted)
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


def _payload(spec: UploadSpec) -> dict[str, object]:
    return {
        "file_name": spec.file_name,
        "content_type": spec.content_type,
        "size_bytes": spec.size_bytes,
    }
