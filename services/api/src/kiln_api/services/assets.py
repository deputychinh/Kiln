"""Asset use cases: create, add a version, confirm an upload, read."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from kiln_api.constants import (
    DOWNLOAD_CACHE_CONTROL,
    DOWNLOAD_URL_LIFETIME_SECONDS,
    DOWNLOAD_URL_WINDOW_SECONDS,
    UPLOAD_URL_TTL_SECONDS,
)
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
from kiln_api.domain.authorization import authorize, visible_owner
from kiln_api.domain.idempotency import request_fingerprint
from kiln_api.domain.identity import Principal
from kiln_api.domain.jobs import new_job
from kiln_api.enums import (
    Action,
    FailureReason,
    JobKind,
    PromotionResult,
    ReviewState,
    VersionStatus,
)
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
    """A version with the URLs of its preview and its original file (None until it is ready)."""

    version: AssetVersion
    thumbnail_url: str | None
    download_url: str | None = None


@dataclass(frozen=True, slots=True)
class AssetCard:
    """An asset with the URL of its cover preview."""

    asset: Asset
    thumbnail_url: str | None
    review_state: ReviewState = ReviewState.IN_REVIEW  # its newest version's (KILN-11)


@dataclass(frozen=True, slots=True)
class AssetDetail:
    """An asset with its cover preview and its versions by number."""

    asset: Asset
    thumbnail_url: str | None
    versions: list[VersionView]
    review_state: ReviewState = ReviewState.IN_REVIEW  # its newest version's (KILN-11)


class AssetService:
    """Coordinates the repository, object storage and the clock.

    Every use case takes the calling `Principal` and asks the authorization policy first
    (ADR 0012); the policy is the only place that decides.
    """

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
        self,
        principal: Principal,
        name: str,
        spec: UploadSpec,
        *,
        idempotency_key: str | None = None,
    ) -> PendingUpload:
        """Store a new asset with version 1, owned by the caller, and sign its upload.

        With an idempotency key, a repeat by the same user within the window replays the first
        result.
        """
        authorize(principal, Action.WRITE_ASSETS)
        payload = {"name": name, **_payload(spec)}
        with self._unit_of_work() as tx:
            replay = self._claim(tx, principal, idempotency_key, "create_asset", payload)
            if replay is not None:
                return self._replayed(tx, replay)
            asset, version = new_asset(
                name,
                spec,
                now=self._clock.now(),
                new_id=self._new_id,
                owner_id=principal.user_id,
            )
            tx.assets.add(asset, version)
            self._complete(tx, principal, idempotency_key, version)
        return PendingUpload(asset=asset, version=version, upload=self._sign(version))

    def add_version(
        self,
        principal: Principal,
        asset_id: UUID,
        spec: UploadSpec,
        *,
        idempotency_key: str | None = None,
    ) -> PendingUpload:
        """Store the next version of an asset, uploaded by the caller, and sign its upload.

        Idempotent per user with a key.
        """
        authorize(principal, Action.WRITE_ASSETS)
        now = self._clock.now()
        operation = f"add_version:{asset_id}"
        with self._unit_of_work() as tx:
            replay = self._claim(tx, principal, idempotency_key, operation, _payload(spec))
            if replay is not None:
                return self._replayed(tx, replay)
            version = tx.assets.add_next_version(
                asset_id,
                lambda asset, number: self._next_version(principal, asset, number, spec, now),
            )
            asset = tx.assets.get(asset_id)
            self._complete(tx, principal, idempotency_key, version)
        return PendingUpload(asset=asset, version=version, upload=self._sign(version))

    def _next_version(
        self, principal: Principal, asset: Asset, number: int, spec: UploadSpec, now: datetime
    ) -> AssetVersion:
        authorize(principal, Action.WRITE_ASSETS, asset)  # under the asset's row lock
        return new_version(
            asset, number, spec, now=now, new_id=self._new_id, uploaded_by=principal.user_id
        )

    def _claim(
        self,
        tx: Transaction,
        principal: Principal,
        key: str | None,
        operation: str,
        payload: dict[str, object],
    ) -> IdempotentResult | None:
        if key is None:
            return None
        return tx.idempotency.claim(
            user_id=principal.user_id,
            key=key,
            operation=operation,
            request_hash=request_fingerprint(operation, payload),
            now=self._clock.now(),
        )

    @staticmethod
    def _complete(
        tx: Transaction, principal: Principal, key: str | None, version: AssetVersion
    ) -> None:
        if key is not None:
            tx.idempotency.complete(
                user_id=principal.user_id,
                key=key,
                asset_id=version.asset_id,
                version_id=version.id,
            )

    def _replayed(self, tx: Transaction, replay: IdempotentResult) -> PendingUpload:
        if replay.asset_id is None or replay.version_id is None:
            raise IdempotencyKeyInUseError  # cannot happen after commit; never replay half a result
        version = tx.assets.get_version(replay.version_id)
        upload = self._sign(version) if version.status is VersionStatus.PENDING_UPLOAD else None
        return PendingUpload(
            asset=tx.assets.get(replay.asset_id), version=version, upload=upload, replayed=True
        )

    def complete_upload(self, principal: Principal, version_id: UUID) -> AssetVersion:
        """Check the stored object against the declaration and start processing.

        The file is copied from the staging key to the final key only if it is byte-for-byte
        the object that was checked (ETag), so a signed form reused later cannot change it.
        Idempotent: a version that already left `pending_upload` is returned unchanged, and a
        retry after a partial failure resumes where it stopped.
        """
        authorize(principal, Action.WRITE_ASSETS)
        version = self._repository.get_version(version_id)
        authorize(principal, Action.WRITE_ASSETS, self._repository.get(version.asset_id))
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

    def get(self, principal: Principal, asset_id: UUID) -> AssetDetail:
        """Return an asset with its cover and versions, each with its preview URL."""
        authorize(principal, Action.READ_ASSETS)
        asset = self._repository.get(asset_id)
        authorize(principal, Action.READ_ASSETS, asset)
        versions = [self._view(v) for v in self._repository.versions_of(asset_id)]
        states = self._repository.newest_review_states([asset_id])
        return AssetDetail(
            asset=asset,
            thumbnail_url=self._cover(asset),
            versions=versions,
            review_state=states.get(asset_id, ReviewState.IN_REVIEW),
        )

    def get_version(self, principal: Principal, version_id: UUID) -> VersionView:
        """Return one version with its preview and file URLs."""
        authorize(principal, Action.READ_ASSETS)
        version = self._repository.get_version(version_id)
        authorize(principal, Action.READ_ASSETS, self._repository.get(version.asset_id))
        return self._view(version)

    def list(self, principal: Principal, *, cursor: str | None, limit: int) -> Page[AssetCard]:
        """Return the assets the caller may see, newest first, each with its cover preview URL."""
        authorize(principal, Action.READ_ASSETS)
        page = self._repository.list_page(
            cursor=cursor, limit=limit, owner_id=visible_owner(principal)
        )
        states = self._repository.newest_review_states([a.id for a in page.items])
        cards = tuple(
            AssetCard(
                asset=a,
                thumbnail_url=self._cover(a),
                review_state=states.get(a.id, ReviewState.IN_REVIEW),
            )
            for a in page.items
        )
        return Page(items=cards, next_cursor=page.next_cursor)

    def _view(self, version: AssetVersion) -> VersionView:
        """Ready versions link their preview and, for the 3D viewer, their original (KILN-9).

        Only a ready file has passed the worker's checks; the key is immutable, so the original
        is signed and cached exactly like a preview (ADR 0008).
        """
        if version.status is not VersionStatus.READY:
            return VersionView(version=version, thumbnail_url=None)
        return VersionView(
            version=version,
            thumbnail_url=self._download_url(thumbnail_key(version)),
            download_url=self._download_url(version.object_key),
        )

    def _cover(self, asset: Asset) -> str | None:
        if asset.cover_version_id is None:
            return None
        return self._download_url(thumbnail_key_for(asset.id, asset.cover_version_id))

    def _download_url(self, key: str) -> str:
        """Sign at the start of the current window, so the URL is the same all window long.

        The browser cache then hits; each URL is valid at least `DOWNLOAD_URL_TTL_SECONDS` after
        it is handed out.
        """
        now = self._clock.now().timestamp()
        window_start = datetime.fromtimestamp(now - now % DOWNLOAD_URL_WINDOW_SECONDS, tz=UTC)
        return self._storage.presign_download(
            key,
            signed_at=window_start,
            ttl_seconds=DOWNLOAD_URL_LIFETIME_SECONDS,
            cache_control=DOWNLOAD_CACHE_CONTROL,
        )

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
