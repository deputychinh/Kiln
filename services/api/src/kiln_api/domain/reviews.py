"""Review states of asset versions and their history (KILN-11): rules only, no I/O.

Every version starts `in_review`. A reviewer approves it or requests changes; either decision is
undone only by reopening it, which puts it back in review. The whole machine is the table below:
an action missing from it is refused, so nothing else can happen to a state.

Every transition is recorded as a `ReviewEvent` (who, when, from, to, an optional note) numbered
per version, and the version's `review_revision` is the number of the last one: a reviewer's
write succeeds only if the state and revision it read are still current (compare-and-set).
"""

from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from kiln_api.constants import REVIEW_NOTE_MAX_LENGTH
from kiln_api.domain.assets import AssetVersion, IdFactory, is_unreadable
from kiln_api.domain.comments import Author
from kiln_api.enums import ReviewAction, ReviewState, VersionStatus
from kiln_api.errors import (
    InvalidReviewNoteError,
    InvalidReviewTransitionError,
    ReviewStateConflictError,
    VersionNotReadyError,
)

_LINE_BREAK = "\n"

# The state machine: (state, action) -> next state. Pinned literally in test_reviews_domain.py.
REVIEW_TRANSITIONS: MappingProxyType[tuple[ReviewState, ReviewAction], ReviewState] = (
    MappingProxyType(
        {
            (ReviewState.IN_REVIEW, ReviewAction.APPROVE): ReviewState.APPROVED,
            (ReviewState.IN_REVIEW, ReviewAction.REQUEST_CHANGES): ReviewState.CHANGES_REQUESTED,
            (ReviewState.APPROVED, ReviewAction.REOPEN): ReviewState.IN_REVIEW,
            (ReviewState.CHANGES_REQUESTED, ReviewAction.REOPEN): ReviewState.IN_REVIEW,
        }
    )
)
# A decision needs something to look at: a version the worker has processed. Reopening does not,
# so a decided version that later failed a re-check (ADR 0011) can still be reopened.
DECISIONS = frozenset({ReviewAction.APPROVE, ReviewAction.REQUEST_CHANGES})


@dataclass(frozen=True, slots=True)
class ReviewEvent:
    """One transition of a version's review state; never changed once written."""

    id: UUID
    version_id: UUID
    sequence: int  # per version, from 1; equals the version's review_revision after it
    action: ReviewAction
    from_state: ReviewState
    to_state: ReviewState
    actor_id: UUID
    note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewEventView:
    """An event with the name of who made it."""

    event: ReviewEvent
    actor: Author


def clean_review_note(raw: str | None) -> str | None:
    """None for no note or a blank one; else the trimmed note with CRLF and CR made LF.

    Raises:
        InvalidReviewNoteError: Longer than the limit, or hiding control or format characters.
    """
    if raw is None:
        return None
    note = raw.replace("\r\n", _LINE_BREAK).replace("\r", _LINE_BREAK).strip()
    if not note:
        return None
    if len(note) > REVIEW_NOTE_MAX_LENGTH or is_unreadable(note.replace(_LINE_BREAK, "")):
        raise InvalidReviewNoteError
    return note


def next_state(state: ReviewState, action: ReviewAction) -> ReviewState:
    """The state `action` leads to from `state`, or `InvalidReviewTransitionError`."""
    try:
        return REVIEW_TRANSITIONS[state, action]
    except KeyError:
        raise InvalidReviewTransitionError(state, action) from None


def decide(  # noqa: PLR0913 - keyword-only facts of one decision
    version: AssetVersion,
    action: ReviewAction,
    *,
    expected_state: ReviewState,
    actor_id: UUID,
    note: str | None,
    now: datetime,
    new_id: IdFactory,
) -> tuple[AssetVersion, ReviewEvent]:
    """Apply `action` to `version` if it is still in `expected_state`; return both new facts.

    Checks, in order: the state the reviewer saw is still current (else a conflict: someone else
    acted first), the table allows the action, a decision is made on a ready version, the note.

    Raises:
        ReviewStateConflictError: The version's state is no longer `expected_state`.
        InvalidReviewTransitionError: The table has no such transition.
        VersionNotReadyError: Approve or request changes on a version that is not ready.
        InvalidReviewNoteError: See `clean_review_note`.
    """
    if version.review_state is not expected_state:
        raise ReviewStateConflictError(version.review_state)
    target = next_state(version.review_state, action)
    if action in DECISIONS and version.status is not VersionStatus.READY:
        raise VersionNotReadyError
    event = ReviewEvent(
        id=new_id(),
        version_id=version.id,
        sequence=version.review_revision + 1,
        action=action,
        from_state=version.review_state,
        to_state=target,
        actor_id=actor_id,
        note=clean_review_note(note),
        created_at=now,
    )
    return replace(version, review_state=target, review_revision=event.sequence), event
