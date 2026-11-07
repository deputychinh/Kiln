"""Comment threads and region annotations on asset versions (KILN-10): rules only, no I/O.

A thread belongs to one version and may mark a region of its image; its first comment is its
root, the rest are replies. Regions are normalised to the image (0 to 1 on each axis, origin top
left), the model Frame.io uses, so they survive any display size and the 512 px previews.
"""

import math
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from kiln_api.constants import COMMENT_BODY_MAX_LENGTH, REGION_MAX, REGION_MIN
from kiln_api.domain.assets import IdFactory, is_unreadable
from kiln_api.enums import RegionShape
from kiln_api.errors import CommentDeletedError, InvalidCommentBodyError, InvalidRegionError

_LINE_BREAK = "\n"


@dataclass(frozen=True, slots=True)
class Region:
    """A rectangle (`width` and `height` set) or a point (both None), normalised to the image."""

    shape: RegionShape
    x: float
    y: float
    width: float | None = None
    height: float | None = None


@dataclass(frozen=True, slots=True)
class Author:
    """Who wrote or resolved something, as other people see them."""

    id: UUID
    display_name: str


@dataclass(frozen=True, slots=True)
class Comment:
    """One message in a thread; a deleted one keeps its place with an empty body."""

    id: UUID
    thread_id: UUID
    author_id: UUID
    body: str
    is_root: bool
    created_at: datetime
    edited_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_deleted(self) -> bool:
        """Soft-deleted: shown as "deleted" so the replies keep their context."""
        return self.deleted_at is not None


@dataclass(frozen=True, slots=True)
class CommentThread:
    """A conversation on one version, numbered per version, optionally on a region."""

    id: UUID
    version_id: UUID
    number: int  # 0 until the store assigns the next number for the version
    author_id: UUID
    region: Region | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    resolved_by: UUID | None = None


def clean_comment_body(raw: str) -> str:
    """Trim a body, CRLF and CR to LF; raise `InvalidCommentBodyError` when it breaks the rules.

    Line breaks are the only control characters allowed; every other rule is the one shared by
    names (no hidden, format or control characters, something visible).
    """
    body = raw.replace("\r\n", _LINE_BREAK).replace("\r", _LINE_BREAK).strip()
    if not body or len(body) > COMMENT_BODY_MAX_LENGTH:
        raise InvalidCommentBodyError
    if is_unreadable(body.replace(_LINE_BREAK, "")):
        raise InvalidCommentBodyError
    return body


def _in_range(value: float) -> bool:
    return math.isfinite(value) and REGION_MIN <= value <= REGION_MAX


def check_region(region: Region) -> Region:
    """Return `region` when it lies inside the image and fits its shape; raise otherwise.

    Raises:
        InvalidRegionError: Out of 0 to 1, not finite, no size for a rectangle or past an edge,
            or a size on a point.
    """
    if not (_in_range(region.x) and _in_range(region.y)):
        raise InvalidRegionError
    if region.shape is RegionShape.POINT:
        if region.width is not None or region.height is not None:
            raise InvalidRegionError
        return region
    width, height = region.width, region.height
    if width is None or height is None or not (_in_range(width) and _in_range(height)):
        raise InvalidRegionError
    if width <= 0 or height <= 0:
        raise InvalidRegionError
    if region.x + width > REGION_MAX or region.y + height > REGION_MAX:
        raise InvalidRegionError
    return region


def new_thread(  # noqa: PLR0913 - keyword-only facts of one thread
    version_id: UUID,
    *,
    author_id: UUID,
    body: str,
    region: Region | None,
    now: datetime,
    new_id: IdFactory,
) -> tuple[CommentThread, Comment]:
    """A thread (numbered by the store) and its first comment."""
    cleaned = clean_comment_body(body)
    thread = CommentThread(
        id=new_id(),
        version_id=version_id,
        number=0,
        author_id=author_id,
        region=None if region is None else check_region(region),
        created_at=now,
        updated_at=now,
    )
    root = Comment(
        id=new_id(),
        thread_id=thread.id,
        author_id=author_id,
        body=cleaned,
        is_root=True,
        created_at=now,
    )
    return thread, root


def new_reply(
    thread: CommentThread, *, author_id: UUID, body: str, now: datetime, new_id: IdFactory
) -> Comment:
    """A reply at the end of `thread`."""
    return Comment(
        id=new_id(),
        thread_id=thread.id,
        author_id=author_id,
        body=clean_comment_body(body),
        is_root=False,
        created_at=now,
    )


def edit_comment(comment: Comment, body: str, *, now: datetime) -> Comment:
    """The comment with a new body, marked edited; a deleted comment stays deleted."""
    if comment.is_deleted:
        raise CommentDeletedError
    return replace(comment, body=clean_comment_body(body), edited_at=now)


def delete_comment(comment: Comment, *, now: datetime) -> Comment:
    """Soft delete: the body goes, the place in the thread stays; repeating changes nothing."""
    if comment.is_deleted:
        return comment
    return replace(comment, body="", deleted_at=now)


def set_resolved(
    thread: CommentThread, *, resolved: bool, by: UUID, now: datetime
) -> CommentThread:
    """Resolve or reopen; resolving a resolved thread keeps who resolved it first."""
    if resolved:
        if thread.resolved_at is not None:
            return thread
        return replace(thread, resolved_at=now, resolved_by=by, updated_at=now)
    if thread.resolved_at is None:
        return thread
    return replace(thread, resolved_at=None, resolved_by=None, updated_at=now)
