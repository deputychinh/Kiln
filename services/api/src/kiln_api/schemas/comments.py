"""Request and response bodies for comment threads, comments and regions (KILN-10)."""

import unicodedata
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kiln_api.constants import MAX_COMMENT_BODY_FIELD_LENGTH
from kiln_api.domain.comments import Author, Region
from kiln_api.enums import RegionShape
from kiln_api.errors import DomainError, InvalidCommentBodyError
from kiln_api.ports import CommentView, Page, ThreadView

_NORMALISED = "Normalised to the image: 0 is the left (top) edge, 1 the right (bottom) edge."


def refuse_lone_surrogates(error: type[DomainError]) -> Callable[[object], object]:
    """A `before` validator that answers a lone surrogate with the field's own domain error.

    A JSON surrogate escape without its pair decodes to a lone surrogate (Unicode category Cs),
    which pydantic would refuse as an invalid string (VALIDATION_FAILED) before the domain sees
    it. It is raised as a domain error, which pydantic does not wrap: 422 with the field's code
    (KILN-10 AC3, KILN-11 notes).
    """

    def check(value: object) -> object:
        if isinstance(value, str) and any(unicodedata.category(char) == "Cs" for char in value):
            raise error
        return value

    return check


class RegionIn(BaseModel):
    """A rectangle (`width` and `height`) or a point (neither), normalised to the image."""

    model_config = ConfigDict(extra="forbid")

    shape: RegionShape
    x: float = Field(
        strict=True, description=f"Left edge of a rectangle, or a point. {_NORMALISED}"
    )
    y: float = Field(strict=True, description=f"Top edge of a rectangle, or a point. {_NORMALISED}")
    width: float | None = Field(
        default=None, strict=True, description="Rectangles only, at least 0.01."
    )
    height: float | None = Field(
        default=None, strict=True, description="Rectangles only, at least 0.01."
    )

    def to_region(self) -> Region:
        """Convert to the domain value (the domain checks the bounds)."""
        return Region(shape=self.shape, x=self.x, y=self.y, width=self.width, height=self.height)


class RegionOut(BaseModel):
    """A region as stored."""

    shape: RegionShape
    x: float
    y: float
    width: float | None
    height: float | None

    @classmethod
    def of(cls, region: Region | None) -> "RegionOut | None":
        """Build from the domain value."""
        if region is None:
            return None
        return cls(
            shape=region.shape, x=region.x, y=region.y, width=region.width, height=region.height
        )


class StartThreadRequest(BaseModel):
    """The first comment of a thread, on a region or on the whole version."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(max_length=MAX_COMMENT_BODY_FIELD_LENGTH)
    region: RegionIn | None = None

    _surrogates = field_validator("body", mode="before")(
        refuse_lone_surrogates(InvalidCommentBodyError)
    )


class CommentRequest(BaseModel):
    """A reply, or the new text of a comment."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(max_length=MAX_COMMENT_BODY_FIELD_LENGTH)

    _surrogates = field_validator("body", mode="before")(
        refuse_lone_surrogates(InvalidCommentBodyError)
    )


class ResolveRequest(BaseModel):
    """Resolve (`true`) or reopen (`false`) a thread."""

    model_config = ConfigDict(extra="forbid")

    resolved: bool = Field(strict=True)


class AuthorOut(BaseModel):
    """Who wrote or resolved something."""

    id: UUID
    display_name: str

    @classmethod
    def of(cls, author: Author) -> "AuthorOut":
        """Build from the domain value."""
        return cls(id=author.id, display_name=author.display_name)


class CommentOut(BaseModel):
    """One comment; a deleted one keeps its place with an empty body."""

    id: UUID
    thread_id: UUID
    author: AuthorOut
    body: str
    created_at: datetime
    edited_at: datetime | None
    deleted: bool

    @classmethod
    def of(cls, view: CommentView) -> "CommentOut":
        """Build from the read model."""
        comment = view.comment
        return cls(
            id=comment.id,
            thread_id=comment.thread_id,
            author=AuthorOut.of(view.author),
            body=comment.body,
            created_at=comment.created_at,
            edited_at=comment.edited_at,
            deleted=comment.is_deleted,
        )


class ThreadOut(BaseModel):
    """A thread with its first comment; replies are read page by page."""

    id: UUID
    version_id: UUID
    number: int = Field(description="Per version, from 1, in the order threads were started.")
    region: RegionOut | None
    comment: CommentOut = Field(description="The first comment.")
    reply_count: int
    resolved_at: datetime | None
    resolved_by: AuthorOut | None
    created_at: datetime

    @classmethod
    def of(cls, view: ThreadView) -> "ThreadOut":
        """Build from the read model."""
        thread = view.thread
        return cls(
            id=thread.id,
            version_id=thread.version_id,
            number=thread.number,
            region=RegionOut.of(thread.region),
            comment=CommentOut.of(view.root),
            reply_count=view.reply_count,
            resolved_at=thread.resolved_at,
            resolved_by=None if view.resolved_by is None else AuthorOut.of(view.resolved_by),
            created_at=thread.created_at,
        )


class ThreadPageOut(BaseModel):
    """A page of threads by number; `next_cursor` is null on the last page."""

    items: list[ThreadOut]
    next_cursor: str | None

    @classmethod
    def of(cls, page: Page[ThreadView]) -> "ThreadPageOut":
        """Build from a page of read models."""
        return cls(items=[ThreadOut.of(v) for v in page.items], next_cursor=page.next_cursor)


class CommentPageOut(BaseModel):
    """A page of replies, oldest first; `next_cursor` is null on the last page."""

    items: list[CommentOut]
    next_cursor: str | None

    @classmethod
    def of(cls, page: Page[CommentView]) -> "CommentPageOut":
        """Build from a page of read models."""
        return cls(items=[CommentOut.of(v) for v in page.items], next_cursor=page.next_cursor)
