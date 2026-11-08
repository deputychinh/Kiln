"""Review use cases (KILN-11): approve, request changes or reopen a version; read its history."""

from uuid import UUID

from kiln_api.domain.assets import IdFactory
from kiln_api.domain.authorization import authorize
from kiln_api.domain.idempotency import request_fingerprint
from kiln_api.domain.identity import Principal
from kiln_api.domain.reviews import ReviewEventView, decide
from kiln_api.enums import Action, ReviewAction, ReviewState
from kiln_api.errors import IdempotencyKeyInUseError
from kiln_api.ports import Clock, Page, Transaction, UnitOfWork
from kiln_api.services.comments import Created


class ReviewService:
    """Every use case asks the authorization policy (ADR 0012) with the version's asset."""

    def __init__(self, clock: Clock, new_id: IdFactory, unit_of_work: UnitOfWork) -> None:
        """Receive every collaborator through its port."""
        self._clock = clock
        self._new_id = new_id
        self._unit_of_work = unit_of_work

    def transition(  # noqa: PLR0913 - keyword-only facts of one decision
        self,
        principal: Principal,
        version_id: UUID,
        *,
        action: ReviewAction,
        expected_state: ReviewState,
        expected_revision: int | None = None,
        note: str | None,
        idempotency_key: str | None = None,
    ) -> Created[ReviewEventView]:
        """Apply `action` if the version is still as the reviewer saw it; return the new event.

        One transaction: the key's claim, the compare-and-set and the event commit together, so a
        refused decision leaves no event and does not use up its key.
        """
        authorize(principal, Action.REVIEW_VERSIONS)
        operation = f"review:{version_id}"
        payload: dict[str, object] = {
            "action": action.value,
            "expected_state": expected_state.value,
            "expected_revision": expected_revision,
            "note": note,
        }
        with self._unit_of_work() as tx:
            replay = self._claim(tx, principal, idempotency_key, operation, payload)
            if replay is not None:
                return Created(tx.reviews.event_view(replay), replayed=True)
            version = tx.assets.get_version(version_id)
            authorize(principal, Action.REVIEW_VERSIONS, tx.assets.get(version.asset_id))
            decided, event = decide(
                version,
                action,
                expected_state=expected_state,
                expected_revision=expected_revision,
                actor_id=principal.user_id,
                note=note,
                now=self._clock.now(),
                new_id=self._new_id,
            )
            tx.reviews.record(version, decided, event)
            if idempotency_key is not None:
                tx.idempotency.complete_resource(
                    user_id=principal.user_id, key=idempotency_key, resource_id=event.id
                )
            return Created(tx.reviews.event_view(event.id))

    def history(
        self, principal: Principal, version_id: UUID, *, cursor: str | None, limit: int
    ) -> Page[ReviewEventView]:
        """A version's review events, newest first."""
        authorize(principal, Action.READ_REVIEWS)
        with self._unit_of_work() as tx:
            version = tx.assets.get_version(version_id)
            authorize(principal, Action.READ_REVIEWS, tx.assets.get(version.asset_id))
            return tx.reviews.history_page(version_id, cursor=cursor, limit=limit)

    def get_event(self, principal: Principal, event_id: UUID) -> ReviewEventView:
        """One review event."""
        authorize(principal, Action.READ_REVIEWS)
        with self._unit_of_work() as tx:
            view = tx.reviews.event_view(event_id)
            version = tx.assets.get_version(view.event.version_id)
            authorize(principal, Action.READ_REVIEWS, tx.assets.get(version.asset_id))
            return view

    def _claim(
        self,
        tx: Transaction,
        principal: Principal,
        key: str | None,
        operation: str,
        payload: dict[str, object],
    ) -> UUID | None:
        """The event an earlier request with this key made, or None for a first request."""
        if key is None:
            return None
        replay = tx.idempotency.claim(
            user_id=principal.user_id,
            key=key,
            operation=operation,
            request_hash=request_fingerprint(operation, payload),
            now=self._clock.now(),
        )
        if replay is None:
            return None
        if replay.resource_id is None:
            raise IdempotencyKeyInUseError  # the key belongs to another kind of request
        return replay.resource_id
