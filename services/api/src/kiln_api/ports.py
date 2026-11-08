"""Abstract ports the services depend on; adapters live in `repositories/` and `adapters/`."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import IO, Protocol
from uuid import UUID

from kiln_api.domain.assets import Asset, AssetVersion
from kiln_api.domain.comments import Author, Comment, CommentThread
from kiln_api.domain.identity import AccessToken, Session, User
from kiln_api.domain.jobs import Job
from kiln_api.domain.reviews import ReviewEvent, ReviewEventView
from kiln_api.enums import PromotionResult, ReviewState, VersionStatus


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

    def presign_download(
        self,
        key: str,
        *,
        signed_at: datetime,
        ttl_seconds: int,
        cache_control: str | None = None,
    ) -> str:
        """A GET URL valid `ttl_seconds` from `signed_at`; signed locally, no network call.

        The same arguments always give the same URL, so browsers can cache what it returns.
        """
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

    def list_page(
        self, *, cursor: str | None, limit: int, owner_id: UUID | None = None
    ) -> Page[Asset]:
        """Return assets newest first after `cursor` (of `owner_id` only when given).

        `limit` is clamped to 1 to 100.
        """
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

    def newest_review_states(self, asset_ids: Sequence[UUID]) -> dict[UUID, ReviewState]:
        """The review state of each asset's newest version (KILN-11), for the given assets."""
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

    def drop_cover(self, version: AssetVersion) -> None:
        """If `version` is the cover, the newest other ready version becomes it (or none)."""
        ...


@dataclass(frozen=True, slots=True)
class IdempotentResult:
    """What a completed idempotent request created."""

    asset_id: UUID | None
    version_id: UUID | None
    resource_id: UUID | None = None  # a comment thread or reply (KILN-10)


class IdempotencyStore(Protocol):
    """Idempotency keys stored in the caller's transaction."""

    def claim(
        self, *, user_id: UUID, key: str, operation: str, request_hash: bytes, now: datetime
    ) -> IdempotentResult | None:
        """Claim `user_id`'s `key` (None) or return the earlier result; raise on reuse or a wait."""
        ...

    def complete(self, *, user_id: UUID, key: str, asset_id: UUID, version_id: UUID) -> None:
        """Record the created ids for `user_id`'s `key`."""
        ...

    def complete_resource(self, *, user_id: UUID, key: str, resource_id: UUID) -> None:
        """Record the one resource (a comment thread or reply) `user_id`'s `key` created."""
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

    def reap(self, job: Job, *, error: str, now: datetime | None = None) -> bool:
        """Mark an exhausted job dead, only if its lease is still expired when written."""
        ...


@dataclass(frozen=True, slots=True)
class CommentView:
    """A comment with its author's name."""

    comment: Comment
    author: Author


@dataclass(frozen=True, slots=True)
class ThreadView:
    """A thread with its first comment, who resolved it and how many replies it has."""

    thread: CommentThread
    root: CommentView
    resolved_by: Author | None
    reply_count: int


class CommentStore(Protocol):
    """Comment threads and comments on asset versions (KILN-10)."""

    def add_thread(self, thread: CommentThread, root: Comment) -> CommentThread:
        """Store a thread with the next number of its version, and its first comment.

        Numbers are taken under a per-version advisory lock, so parallel threads never share one.
        """
        ...

    def get_thread(self, thread_id: UUID, *, for_update: bool = False) -> CommentThread:
        """Return a thread (row-locked when `for_update`) or raise `CommentThreadNotFoundError`."""
        ...

    def thread_view(self, thread_id: UUID) -> ThreadView:
        """A thread as listed, or raise `CommentThreadNotFoundError`."""
        ...

    def threads_page(self, version_id: UUID, *, cursor: str | None, limit: int) -> Page[ThreadView]:
        """A version's threads oldest first (by creation, so by number) after `cursor`."""
        ...

    def save_thread(self, thread: CommentThread) -> None:
        """Persist a thread's resolution."""
        ...

    def add_comment(self, comment: Comment) -> None:
        """Store a reply."""
        ...

    def get_comment(self, comment_id: UUID, *, for_update: bool = False) -> Comment:
        """Return a comment (row-locked when `for_update`) or raise `CommentNotFoundError`."""
        ...

    def comment_view(self, comment_id: UUID) -> CommentView:
        """A comment with its author, or raise `CommentNotFoundError`."""
        ...

    def replies_page(self, thread_id: UUID, *, cursor: str | None, limit: int) -> Page[CommentView]:
        """A thread's replies (its first comment excluded) oldest first after `cursor`."""
        ...

    def save_comment(self, comment: Comment) -> None:
        """Persist an edit or a soft delete."""
        ...


class ReviewStore(Protocol):
    """Review states of versions and their append-only history (KILN-11)."""

    def record(self, read: AssetVersion, decided: AssetVersion, event: ReviewEvent) -> None:
        """Write `decided`'s review state and append `event`, if `read` is still current.

        Compare-and-set on the state and revision of `read` (and, for a decision, on the version
        still being ready); the event goes in the same transaction.

        Raises:
            ReviewStateConflictError: Another reviewer changed the state or revision meanwhile.
            VersionNotReadyError: A decision on a version that stopped being ready meanwhile.
            AssetVersionNotFoundError: The version is gone.
        """
        ...

    def event_view(self, event_id: UUID) -> ReviewEventView:
        """One event with its actor, or raise `ReviewEventNotFoundError`."""
        ...

    def history_page(
        self, version_id: UUID, *, cursor: str | None, limit: int
    ) -> Page[ReviewEventView]:
        """A version's events newest first, after `cursor`."""
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

    @property
    def comments(self) -> CommentStore:
        """Comment threads and comments in this transaction."""
        ...

    @property
    def reviews(self) -> ReviewStore:
        """Review states and history in this transaction."""
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

    def ready_model_versions(self, *, after: UUID | None, limit: int) -> list[UUID]:
        """Ids of ready versions of model assets after `after`, by id (KILN-36 re-check)."""
        ...


class PasswordHasher(Protocol):
    """Slow, salted password hashing (Argon2id); never raises on a wrong password."""

    def hash(self, password: str) -> str:
        """A PHC string with the current parameters."""
        ...

    def verify(self, password_hash: str, password: str) -> bool:
        """True when `password` matches; False for a wrong password or a malformed hash."""
        ...

    def needs_rehash(self, password_hash: str) -> bool:
        """True when the hash was made with other parameters than the current ones."""
        ...


@dataclass(frozen=True, slots=True)
class FailureCounts:
    """Failed sign-ins in the window, per account and per client IP, with the oldest of each."""

    account: int
    ip: int
    oldest_account: datetime | None
    oldest_ip: datetime | None


class IdentityStore(Protocol):
    """Users, sessions, access tokens and sign-in failures (KILN-12)."""

    def add_user(self, user: User) -> None:
        """Store a new user; raise `EmailTakenError` when the email is in use."""
        ...

    def user_by_email(self, email: str) -> User | None:
        """The user with this normalised email, if any."""
        ...

    def set_password_hash(self, user_id: UUID, password_hash: str, *, now: datetime) -> None:
        """Replace a user's password hash (re-hash on sign-in after a parameter change)."""
        ...

    def add_session(self, session: Session) -> None:
        """Store a new session."""
        ...

    def session_user(self, id_hash: bytes) -> tuple[Session, User] | None:
        """The session with this id hash and its user, in one query."""
        ...

    def touch_session(self, id_hash: bytes, *, now: datetime) -> None:
        """Record activity (moves the idle bound)."""
        ...

    def delete_session(self, id_hash: bytes) -> None:
        """End a session; a missing one is not an error."""
        ...

    def purge_sessions(self, *, now: datetime, idle: timedelta) -> int:
        """Delete sessions past their absolute bound or idle for longer than `idle`."""
        ...

    def add_token(self, token: AccessToken) -> None:
        """Store a new access token."""
        ...

    def token_user(self, token_hash: bytes) -> tuple[AccessToken, User] | None:
        """The token with this hash and its user, in one query."""
        ...

    def tokens_of(self, user_id: UUID, *, limit: int) -> list[AccessToken]:
        """A user's tokens that are not revoked, newest first."""
        ...

    def count_live_tokens(self, user_id: UUID, *, now: datetime) -> int:
        """How many of a user's tokens are neither revoked nor expired."""
        ...

    def revoke_token(self, user_id: UUID, token_id: UUID, *, now: datetime) -> bool:
        """Revoke one of `user_id`'s tokens; False when it is not theirs or already revoked."""
        ...

    def touch_token(self, token_id: UUID, *, now: datetime) -> None:
        """Record when a token was last used."""
        ...

    def reserve_attempt(  # noqa: PLR0913 - keyword-only facts of one attempt
        self,
        *,
        attempt_id: UUID,
        account_key: bytes,
        client_ip: str,
        now: datetime,
        since: datetime,
        limits: tuple[int, int],
    ) -> FailureCounts | None:
        """Count recent failures and, under both limits, record this attempt as one.

        Serialised per account and per IP (advisory locks), so parallel attempts can never check
        more passwords than the limits allow. Returns the counts when a limit is reached (nothing
        recorded), None once the attempt is recorded; a successful sign-in then clears it.
        """
        ...

    def clear_failures(self, account_key: bytes) -> None:
        """Forget an account's failures after it signs in."""
        ...
