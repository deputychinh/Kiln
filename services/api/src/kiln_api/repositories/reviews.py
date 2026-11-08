"""Postgres adapter for the `ReviewStore` port (KILN-11)."""

from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Row, Select, insert, select, update

from kiln_api.constants import REVIEW_PAGE_LIMIT_MAX, REVIEW_PAGE_LIMIT_MIN
from kiln_api.db.schema import asset_versions, review_events, users
from kiln_api.domain.assets import AssetVersion
from kiln_api.domain.comments import Author
from kiln_api.domain.cursor import decode_number_cursor, encode_number_cursor
from kiln_api.domain.reviews import DECISIONS, ReviewEvent, ReviewEventView
from kiln_api.enums import ReviewAction, ReviewState, VersionStatus
from kiln_api.errors import (
    AssetVersionNotFoundError,
    ReviewEventNotFoundError,
    ReviewStateConflictError,
    VersionNotReadyError,
)
from kiln_api.ports import Page


def _event_query() -> Select[Any]:
    return select(review_events, users.c.display_name.label("actor_name")).join(
        users, users.c.id == review_events.c.actor_id
    )


def _event_view(row: Row[Any]) -> ReviewEventView:
    event = ReviewEvent(
        id=row.id,
        version_id=row.version_id,
        sequence=row.sequence,
        action=ReviewAction(row.action),
        from_state=ReviewState(row.from_state),
        to_state=ReviewState(row.to_state),
        actor_id=row.actor_id,
        note=row.note,
        created_at=row.created_at,
    )
    return ReviewEventView(event=event, actor=Author(id=row.actor_id, display_name=row.actor_name))


class SqlReviewStore:
    """Writes review states and events in the caller's transaction (a unit of work's connection)."""

    def __init__(self, connection: Connection) -> None:
        """Join the transaction of `connection`."""
        self._connection = connection

    def record(self, read: AssetVersion, decided: AssetVersion, event: ReviewEvent) -> None:
        """Compare-and-set the version's review state, then append the event.

        The guard re-checks, in the write itself, everything the decision was made on: the state
        and revision that were read and, for approve or request changes, that the version is still
        ready (a worker re-check can fail it meanwhile). Under READ COMMITTED a second reviewer's
        UPDATE waits for the first one's row lock, then re-evaluates the guard on the committed
        row, matches nothing and is refused: exactly one of two concurrent decisions wins.
        """
        guard = [
            asset_versions.c.id == read.id,
            asset_versions.c.review_state == read.review_state.value,
            asset_versions.c.review_revision == read.review_revision,
        ]
        if event.action in DECISIONS:
            guard.append(asset_versions.c.status == VersionStatus.READY.value)
        result = self._connection.execute(
            update(asset_versions)
            .where(*guard)
            .values(
                review_state=decided.review_state.value,
                review_revision=decided.review_revision,
            )
        )
        if result.rowcount != 1:
            self._refuse(read)
        self._connection.execute(
            insert(review_events).values(
                id=event.id,
                version_id=event.version_id,
                sequence=event.sequence,
                action=event.action.value,
                from_state=event.from_state.value,
                to_state=event.to_state.value,
                actor_id=event.actor_id,
                note=event.note,
                created_at=event.created_at,
            )
        )

    def _refuse(self, read: AssetVersion) -> None:
        """Explain why the compare-and-set matched nothing, from the row as it is now."""
        row = self._connection.execute(
            select(
                asset_versions.c.status,
                asset_versions.c.review_state,
                asset_versions.c.review_revision,
            ).where(asset_versions.c.id == read.id)
        ).one_or_none()
        if row is None:
            raise AssetVersionNotFoundError(read.id)
        if (
            row.review_state != read.review_state.value
            or row.review_revision != read.review_revision
        ):
            raise ReviewStateConflictError(ReviewState(row.review_state))
        raise VersionNotReadyError

    def event_view(self, event_id: UUID) -> ReviewEventView:
        """One event with its actor's name."""
        row = self._connection.execute(
            _event_query().where(review_events.c.id == event_id)
        ).one_or_none()
        if row is None:
            raise ReviewEventNotFoundError(event_id)
        return _event_view(row)

    def history_page(
        self, version_id: UUID, *, cursor: str | None, limit: int
    ) -> Page[ReviewEventView]:
        """Newest first: keyset on `uq_review_events_version_id_sequence`, read backwards.

        The sequence is taken under the version's compare-and-set, so it is gap-free and in commit
        order per version; a page never skips an event that commits while it is read.
        """
        size = max(REVIEW_PAGE_LIMIT_MIN, min(REVIEW_PAGE_LIMIT_MAX, limit))
        query = (
            _event_query()
            .where(review_events.c.version_id == version_id)
            .order_by(review_events.c.sequence.desc())
        )
        if cursor is not None:
            query = query.where(review_events.c.sequence < decode_number_cursor(cursor))
        rows = self._connection.execute(query.limit(size + 1)).all()
        items = tuple(_event_view(row) for row in rows[:size])
        last = items[-1].event if len(rows) > size and items else None
        return Page(
            items=items,
            next_cursor=None if last is None else encode_number_cursor(last.sequence),
        )
