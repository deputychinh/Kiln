"""Comment use cases (KILN-10): threads with regions on a version, replies, edits, resolution."""

from dataclasses import dataclass
from uuid import UUID

from kiln_api.domain.assets import Asset, IdFactory
from kiln_api.domain.authorization import authorize
from kiln_api.domain.comments import (
    Region,
    delete_comment,
    edit_comment,
    new_reply,
    new_thread,
    set_resolved,
)
from kiln_api.domain.idempotency import request_fingerprint
from kiln_api.domain.identity import Principal
from kiln_api.enums import Action, AssetKind
from kiln_api.errors import IdempotencyKeyInUseError, RegionNotSupportedError
from kiln_api.ports import (
    Clock,
    CommentView,
    IdempotentResult,
    Page,
    ThreadView,
    Transaction,
    UnitOfWork,
)


@dataclass(frozen=True, slots=True)
class Created[T]:
    """What a create returned, and whether it replays an earlier request with the same key."""

    item: T
    replayed: bool = False


class CommentService:
    """Every use case asks the authorization policy (ADR 0012) with the version's asset.

    Reading an asset is what lets a person read and write its comments (one studio per
    deployment); a token still needs `read` to read and `write` to write.
    """

    def __init__(self, clock: Clock, new_id: IdFactory, unit_of_work: UnitOfWork) -> None:
        """Receive every collaborator through its port."""
        self._clock = clock
        self._new_id = new_id
        self._unit_of_work = unit_of_work

    def list_threads(
        self, principal: Principal, version_id: UUID, *, cursor: str | None, limit: int
    ) -> Page[ThreadView]:
        """A version's threads by number, each with its first comment and reply count."""
        authorize(principal, Action.READ_COMMENTS)
        with self._unit_of_work() as tx:
            self._authorize_version(tx, principal, Action.READ_COMMENTS, version_id)
            return tx.comments.threads_page(version_id, cursor=cursor, limit=limit)

    def start_thread(
        self,
        principal: Principal,
        version_id: UUID,
        *,
        body: str,
        region: Region | None,
        idempotency_key: str | None = None,
    ) -> Created[ThreadView]:
        """Start a thread on a version, on a region of its image or on the whole version."""
        authorize(principal, Action.WRITE_COMMENTS)
        operation = f"start_thread:{version_id}"
        payload: dict[str, object] = {"body": body, "region": _region_payload(region)}
        with self._unit_of_work() as tx:
            replay = self._claim(tx, principal, idempotency_key, operation, payload)
            if replay is not None:
                return Created(tx.comments.thread_view(_created_id(replay)), replayed=True)
            kind = self._authorize_version(tx, principal, Action.WRITE_COMMENTS, version_id)
            if region is not None and kind is not AssetKind.IMAGE:
                raise RegionNotSupportedError
            thread, root = new_thread(
                version_id,
                author_id=principal.user_id,
                body=body,
                region=region,
                now=self._clock.now(),
                new_id=self._new_id,
            )
            stored = tx.comments.add_thread(thread, root)
            self._complete(tx, principal, idempotency_key, stored.id)
            return Created(tx.comments.thread_view(stored.id))

    def get_thread(self, principal: Principal, thread_id: UUID) -> ThreadView:
        """One thread as a page lists it."""
        authorize(principal, Action.READ_COMMENTS)
        with self._unit_of_work() as tx:
            view = tx.comments.thread_view(thread_id)
            self._authorize_version(tx, principal, Action.READ_COMMENTS, view.thread.version_id)
            return view

    def get_comment(self, principal: Principal, comment_id: UUID) -> CommentView:
        """One comment with its author."""
        authorize(principal, Action.READ_COMMENTS)
        with self._unit_of_work() as tx:
            view = tx.comments.comment_view(comment_id)
            thread = tx.comments.get_thread(view.comment.thread_id)
            self._authorize_version(tx, principal, Action.READ_COMMENTS, thread.version_id)
            return view

    def list_replies(
        self, principal: Principal, thread_id: UUID, *, cursor: str | None, limit: int
    ) -> Page[CommentView]:
        """A thread's replies oldest first, without its first comment."""
        authorize(principal, Action.READ_COMMENTS)
        with self._unit_of_work() as tx:
            thread = tx.comments.get_thread(thread_id)
            self._authorize_version(tx, principal, Action.READ_COMMENTS, thread.version_id)
            return tx.comments.replies_page(thread_id, cursor=cursor, limit=limit)

    def reply(
        self,
        principal: Principal,
        thread_id: UUID,
        *,
        body: str,
        idempotency_key: str | None = None,
    ) -> Created[CommentView]:
        """Add a reply at the end of a thread (resolved or not: replying does not reopen it)."""
        authorize(principal, Action.WRITE_COMMENTS)
        operation = f"reply:{thread_id}"
        with self._unit_of_work() as tx:
            replay = self._claim(tx, principal, idempotency_key, operation, {"body": body})
            if replay is not None:
                return Created(tx.comments.comment_view(_created_id(replay)), replayed=True)
            thread = tx.comments.get_thread(thread_id)
            self._authorize_version(tx, principal, Action.WRITE_COMMENTS, thread.version_id)
            comment = new_reply(
                thread,
                author_id=principal.user_id,
                body=body,
                now=self._clock.now(),
                new_id=self._new_id,
            )
            tx.comments.add_comment(comment)
            self._complete(tx, principal, idempotency_key, comment.id)
            return Created(tx.comments.comment_view(comment.id))

    def edit(self, principal: Principal, comment_id: UUID, *, body: str) -> CommentView:
        """Replace the body of the caller's own comment."""
        authorize(principal, Action.WRITE_COMMENTS)
        with self._unit_of_work() as tx:
            comment = tx.comments.get_comment(comment_id, for_update=True)
            self._authorize_comment(tx, principal, comment.thread_id, comment.author_id)
            tx.comments.save_comment(edit_comment(comment, body, now=self._clock.now()))
            return tx.comments.comment_view(comment_id)

    def delete(self, principal: Principal, comment_id: UUID) -> None:
        """Soft-delete the caller's own comment; deleting it again changes nothing."""
        authorize(principal, Action.WRITE_COMMENTS)
        with self._unit_of_work() as tx:
            comment = tx.comments.get_comment(comment_id, for_update=True)
            self._authorize_comment(tx, principal, comment.thread_id, comment.author_id)
            deleted = delete_comment(comment, now=self._clock.now())
            if deleted is not comment:
                tx.comments.save_comment(deleted)

    def resolve(self, principal: Principal, thread_id: UUID, *, resolved: bool) -> ThreadView:
        """Resolve or reopen a thread; anyone who may comment may do either."""
        authorize(principal, Action.WRITE_COMMENTS)
        with self._unit_of_work() as tx:
            # Locked: two people resolving at once keep the first resolution.
            thread = tx.comments.get_thread(thread_id, for_update=True)
            self._authorize_version(tx, principal, Action.WRITE_COMMENTS, thread.version_id)
            changed = set_resolved(
                thread, resolved=resolved, by=principal.user_id, now=self._clock.now()
            )
            if changed is not thread:
                tx.comments.save_thread(changed)
            return tx.comments.thread_view(thread_id)

    @staticmethod
    def _asset_of(tx: Transaction, version_id: UUID) -> Asset:
        """The asset a version belongs to: what the policy decides on."""
        return tx.assets.get(tx.assets.get_version(version_id).asset_id)

    def _authorize_version(
        self, tx: Transaction, principal: Principal, action: Action, version_id: UUID
    ) -> AssetKind:
        """Check `action` against the asset the version belongs to; return the asset's kind."""
        asset = self._asset_of(tx, version_id)
        authorize(principal, action, asset)
        return asset.kind

    def _authorize_comment(
        self, tx: Transaction, principal: Principal, thread_id: UUID, author_id: UUID
    ) -> None:
        """Only the author changes a comment, and only on an asset they can reach."""
        asset = self._asset_of(tx, tx.comments.get_thread(thread_id).version_id)
        authorize(principal, Action.CHANGE_OWN_COMMENT, asset, author_id=author_id)

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
        tx: Transaction, principal: Principal, key: str | None, resource_id: UUID
    ) -> None:
        if key is not None:
            tx.idempotency.complete_resource(
                user_id=principal.user_id, key=key, resource_id=resource_id
            )


def _created_id(replay: IdempotentResult) -> UUID:
    if replay.resource_id is None:
        raise IdempotencyKeyInUseError  # the key belongs to another kind of request
    return replay.resource_id


def _region_payload(region: Region | None) -> dict[str, object] | None:
    if region is None:
        return None
    return {
        "shape": region.shape.value,
        "x": region.x,
        "y": region.y,
        "width": region.width,
        "height": region.height,
    }
