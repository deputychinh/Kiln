"""Asset use cases: create, add a version, confirm an upload, read."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from kiln_api.constants import DOWNLOAD_URL_TTL_SECONDS, UPLOAD_URL_TTL_SECONDS
from kiln_api.domain.assets import (
    Asset,
    AssetVersion,
    IdFactory,
    UploadSpec,
    new_asset,
    new_version,
    thumbnail_key,
    thumbnail_key_for,
    transition,
    upload_key,
)
from kiln_api.domain.idempotency import request_fingerprint
from kiln_api.domain.jobs import new_job
from kiln_api.enums import FailureReason, JobKind, PromotionResult, VersionStatus
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
class VersionView:
    """A version with the URL of its preview (None until it is ready)."""

    version: AssetVersion
    thumbnail_url: str | None


@dataclass(frozen=True, slots=True)
class AssetCard:
    """An asset with the URL of its cover preview."""

    asset: Asset
    thumbnail_url: str | None


@dataclass(frozen=True, slots=True)
class AssetDetail:
    """An asset with its cover preview and its versions by number."""

    asset: Asset
    thumbnail_url: str | None
    versions: list[VersionView]


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
        self._promote_staging(version)
        # The final object is the one processing will read; record its ETag (ADR 0005).
        final = self._storage.head(version.object_key)
        if final is None:
            current = self._repository.get_version(version_id)
            if current.status is not VersionStatus.PENDING_UPLOAD:
                return current  # expired (and cleaned up) by maintenance meanwhile
            raise UploadNotFoundError
        self._check_declared(version, final)
        now = self._clock.now()
        processing = replace(
            transition(version, VersionStatus.PROCESSING, now=now), etag=final.etag
        )
        job = new_job(JobKind.THUMBNAIL, version.id, job_id=self._new_id(), now=now)
        try:
            with self._unit_of_work() as tx:  # status, ETag and job commit together (outbox)
                tx.assets.save_version(processing, expected=VersionStatus.PENDING_UPLOAD)
                tx.jobs.enqueue(job)
        except InvalidStatusTransitionError:
            current = self._repository.get_version(version_id)  # someone else moved it first
            if current.failure_reason is FailureReason.UPLOAD_EXPIRED:
                # Maintenance expired it while this copy was running: the promoted file is
                # garbage, and whichever side finishes last removes it (KILN-22).
                self._storage.delete(version.object_key)
            return current
        return processing

    def _promote_staging(self, version: AssetVersion) -> None:
        """Copy the checked staging object to the final key, then drop the staging object.

        A staging object already gone means an earlier attempt (or a concurrent completion)
        promoted it; the caller then checks the final object.
        """
        staging = upload_key(version)
        stored = self._storage.head(staging)
        if stored is None:
            return
        self._check_declared(version, stored)
        result = self._storage.promote(
            source_key=staging, target_key=version.object_key, etag=stored.etag
        )
        if result is PromotionResult.CHANGED:
            raise UploadMismatchError  # replaced between the check and the copy
        if result is PromotionResult.PROMOTED:
            self._storage.delete(staging)

    def get(self, asset_id: UUID) -> AssetDetail:
        """Return an asset with its cover and versions, each with its preview URL."""
        asset = self._repository.get(asset_id)
        versions = [
            VersionView(version=v, thumbnail_url=self._version_thumbnail(v))
            for v in self._repository.versions_of(asset_id)
        ]
        return AssetDetail(asset=asset, thumbnail_url=self._cover(asset), versions=versions)

    def get_version(self, version_id: UUID) -> VersionView:
        """Return one version with its preview URL."""
        version = self._repository.get_version(version_id)
        return VersionView(version=version, thumbnail_url=self._version_thumbnail(version))

    def list(self, *, cursor: str | None, limit: int) -> Page[AssetCard]:
        """Return assets newest first, each with its cover preview URL."""
        page = self._repository.list_page(cursor=cursor, limit=limit)
        cards = tuple(AssetCard(asset=a, thumbnail_url=self._cover(a)) for a in page.items)
        return Page(items=cards, next_cursor=page.next_cursor)

    def _version_thumbnail(self, version: AssetVersion) -> str | None:
        if version.status is not VersionStatus.READY:
            return None
        return self._storage.presign_download(thumbnail_key(version), DOWNLOAD_URL_TTL_SECONDS)

    def _cover(self, asset: Asset) -> str | None:
        if asset.cover_version_id is None:
            return None
        key = thumbnail_key_for(asset.id, asset.cover_version_id)
        return self._storage.presign_download(key, DOWNLOAD_URL_TTL_SECONDS)

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
