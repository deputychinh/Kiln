"""Request and response bodies for review states and history (KILN-11)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kiln_api.constants import MAX_COMMENT_BODY_FIELD_LENGTH
from kiln_api.domain.reviews import ReviewEventView
from kiln_api.enums import ReviewAction, ReviewState
from kiln_api.errors import InvalidReviewNoteError
from kiln_api.ports import Page
from kiln_api.schemas.comments import AuthorOut, refuse_lone_surrogates


class ReviewTransitionRequest(BaseModel):
    """Approve, request changes or reopen, if the version is still in `expected_state`."""

    model_config = ConfigDict(extra="forbid")

    action: ReviewAction = Field(
        description=(
            "`approve` and `request_changes` from `in_review` (a ready version only); `reopen`"
            " from `approved` or `changes_requested` back to `in_review`."
        )
    )
    expected_state: ReviewState = Field(
        description=(
            "The state you saw. If someone changed it since, nothing happens and the answer is"
            " 409 `REVIEW_STATE_CONFLICT` with `current_state`."
        )
    )
    note: str | None = Field(
        default=None,
        max_length=MAX_COMMENT_BODY_FIELD_LENGTH,
        description="Optional, up to 1,000 characters after trimming; blank means none.",
    )

    _surrogates = field_validator("note", mode="before")(
        refuse_lone_surrogates(InvalidReviewNoteError)
    )


class ReviewEventOut(BaseModel):
    """One transition of a version's review state: who, when, from, to and why."""

    id: UUID
    version_id: UUID
    sequence: int = Field(
        description="Per version, from 1; the version's review_revision after it."
    )
    action: ReviewAction
    from_state: ReviewState
    to_state: ReviewState
    actor: AuthorOut
    note: str | None
    created_at: datetime

    @classmethod
    def of(cls, view: ReviewEventView) -> "ReviewEventOut":
        """Build from the read model."""
        event = view.event
        return cls(
            id=event.id,
            version_id=event.version_id,
            sequence=event.sequence,
            action=event.action,
            from_state=event.from_state,
            to_state=event.to_state,
            actor=AuthorOut.of(view.actor),
            note=event.note,
            created_at=event.created_at,
        )


class ReviewEventPageOut(BaseModel):
    """A page of review events, newest first; `next_cursor` is null on the last page."""

    items: list[ReviewEventOut]
    next_cursor: str | None

    @classmethod
    def of(cls, page: Page[ReviewEventView]) -> "ReviewEventPageOut":
        """Build from a page of read models."""
        return cls(items=[ReviewEventOut.of(v) for v in page.items], next_cursor=page.next_cursor)
