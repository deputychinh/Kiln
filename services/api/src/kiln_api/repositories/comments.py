"""Postgres adapter for the `CommentStore` port (KILN-10)."""

from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Row, Select, func, insert, select, text, tuple_, update

from kiln_api.constants import COMMENT_PAGE_LIMIT_MAX, COMMENT_PAGE_LIMIT_MIN
from kiln_api.db.schema import comment_threads, comments, users
from kiln_api.domain.comments import Author, Comment, CommentThread, Region
from kiln_api.domain.cursor import (
    decode_cursor,
    decode_number_cursor,
    encode_cursor,
    encode_number_cursor,
)
from kiln_api.enums import RegionShape
from kiln_api.errors import CommentNotFoundError, CommentThreadNotFoundError
from kiln_api.ports import CommentView, Page, ThreadView

_ROOT = comments.alias("root")
_ROOT_AUTHOR = users.alias("root_author")
_RESOLVER = users.alias("resolver")
_REPLIES = comments.alias("replies")
_COMMENT_AUTHOR = users.alias("comment_author")
# Keyed per version; the namespace keeps it apart from other advisory locks (sign-in throttling).
_NUMBER_LOCK = text(
    "SELECT pg_advisory_xact_lock(hashtextextended('comment-thread:' || :version, 0))"
)


def _size(limit: int) -> int:
    return max(COMMENT_PAGE_LIMIT_MIN, min(COMMENT_PAGE_LIMIT_MAX, limit))


def _region(row: Row[Any]) -> Region | None:
    if row.region_shape is None:
        return None
    return Region(
        shape=RegionShape(row.region_shape),
        x=row.region_x,
        y=row.region_y,
        width=row.region_width,
        height=row.region_height,
    )


def _thread(row: Row[Any]) -> CommentThread:
    return CommentThread(
        id=row.id,
        version_id=row.version_id,
        number=row.number,
        author_id=row.author_id,
        region=_region(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
        resolved_by=row.resolved_by,
    )


def _comment(row: Row[Any], prefix: str = "") -> Comment:
    mapping = row._mapping
    return Comment(
        id=mapping[f"{prefix}id"],
        thread_id=mapping[f"{prefix}thread_id"],
        author_id=mapping[f"{prefix}author_id"],
        body=mapping[f"{prefix}body"],
        is_root=mapping[f"{prefix}is_root"],
        created_at=mapping[f"{prefix}created_at"],
        edited_at=mapping[f"{prefix}edited_at"],
        deleted_at=mapping[f"{prefix}deleted_at"],
    )


def _thread_values(thread: CommentThread) -> dict[str, object]:
    region = thread.region
    return {
        "region_shape": None if region is None else region.shape.value,
        "region_x": None if region is None else region.x,
        "region_y": None if region is None else region.y,
        "region_width": None if region is None else region.width,
        "region_height": None if region is None else region.height,
        "resolved_at": thread.resolved_at,
        "resolved_by": thread.resolved_by,
        "updated_at": thread.updated_at,
    }


def _comment_values(comment: Comment) -> dict[str, object]:
    return {"body": comment.body, "edited_at": comment.edited_at, "deleted_at": comment.deleted_at}


def _thread_query() -> Select[Any]:
    """Threads with their root comment, its author, the resolver and the reply count: one query."""
    reply_count = (
        select(func.count())
        .where(_REPLIES.c.thread_id == comment_threads.c.id, _REPLIES.c.is_root.is_(False))
        .scalar_subquery()
        .label("reply_count")
    )
    root_columns = [column.label(f"root_{column.name}") for column in _ROOT.c]
    return (
        select(
            comment_threads,
            *root_columns,
            _ROOT_AUTHOR.c.display_name.label("root_author_name"),
            _RESOLVER.c.display_name.label("resolver_name"),
            reply_count,
        )
        .join(_ROOT, (_ROOT.c.thread_id == comment_threads.c.id) & _ROOT.c.is_root)
        .join(_ROOT_AUTHOR, _ROOT_AUTHOR.c.id == _ROOT.c.author_id)
        .outerjoin(_RESOLVER, _RESOLVER.c.id == comment_threads.c.resolved_by)
    )


def _thread_view(row: Row[Any]) -> ThreadView:
    root = _comment(row, "root_")
    resolver = (
        None
        if row.resolved_by is None
        else Author(id=row.resolved_by, display_name=row.resolver_name)
    )
    return ThreadView(
        thread=_thread(row),
        root=CommentView(
            comment=root, author=Author(id=root.author_id, display_name=row.root_author_name)
        ),
        resolved_by=resolver,
        reply_count=row.reply_count,
    )


def _comment_query() -> Select[Any]:
    return select(comments, _COMMENT_AUTHOR.c.display_name.label("author_name")).join(
        _COMMENT_AUTHOR, _COMMENT_AUTHOR.c.id == comments.c.author_id
    )


def _comment_view(row: Row[Any]) -> CommentView:
    comment = _comment(row)
    return CommentView(
        comment=comment, author=Author(id=comment.author_id, display_name=row.author_name)
    )


class SqlCommentStore:
    """Stores threads and comments in the caller's transaction (a unit of work's connection)."""

    def __init__(self, connection: Connection) -> None:
        """Join the transaction of `connection`."""
        self._connection = connection

    def add_thread(self, thread: CommentThread, root: Comment) -> CommentThread:
        """Number the thread after its version's last one, under a per-version lock; store it."""
        self._connection.execute(_NUMBER_LOCK, {"version": str(thread.version_id)})
        last = self._connection.execute(
            select(func.coalesce(func.max(comment_threads.c.number), 0)).where(
                comment_threads.c.version_id == thread.version_id
            )
        ).scalar_one()
        numbered = CommentThread(
            id=thread.id,
            version_id=thread.version_id,
            number=last + 1,
            author_id=thread.author_id,
            region=thread.region,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
        self._connection.execute(
            insert(comment_threads).values(
                id=numbered.id,
                version_id=numbered.version_id,
                number=numbered.number,
                author_id=numbered.author_id,
                created_at=numbered.created_at,
                **_thread_values(numbered),
            )
        )
        self._insert_comment(root)
        return numbered

    def get_thread(self, thread_id: UUID, *, for_update: bool = False) -> CommentThread:
        """Return the thread with `thread_id`; `for_update` holds its row until commit."""
        query = select(comment_threads).where(comment_threads.c.id == thread_id)
        if for_update:
            query = query.with_for_update()
        row = self._connection.execute(query).one_or_none()
        if row is None:
            raise CommentThreadNotFoundError(thread_id)
        return _thread(row)

    def thread_view(self, thread_id: UUID) -> ThreadView:
        """The thread as a page lists it."""
        row = self._connection.execute(
            _thread_query().where(comment_threads.c.id == thread_id)
        ).one_or_none()
        if row is None:
            raise CommentThreadNotFoundError(thread_id)
        return _thread_view(row)

    def threads_page(self, version_id: UUID, *, cursor: str | None, limit: int) -> Page[ThreadView]:
        """Keyset pagination on the thread number (`uq_comment_threads_version_id_number`).

        Numbers, not creation times: under the advisory lock a thread created a moment earlier
        can take the later number, and the list must read 1, 2, 3.
        """
        size = _size(limit)
        query = (
            _thread_query()
            .where(comment_threads.c.version_id == version_id)
            .order_by(comment_threads.c.number)
        )
        if cursor is not None:
            query = query.where(comment_threads.c.number > decode_number_cursor(cursor))
        rows = self._connection.execute(query.limit(size + 1)).all()
        items = tuple(_thread_view(row) for row in rows[:size])
        last = items[-1].thread if len(rows) > size and items else None
        return Page(
            items=items,
            next_cursor=None if last is None else encode_number_cursor(last.number),
        )

    def save_thread(self, thread: CommentThread) -> None:
        """Write the resolution of an existing thread."""
        self._connection.execute(
            update(comment_threads)
            .where(comment_threads.c.id == thread.id)
            .values(**_thread_values(thread))
        )

    def add_comment(self, comment: Comment) -> None:
        """Insert a reply."""
        self._insert_comment(comment)

    def _insert_comment(self, comment: Comment) -> None:
        self._connection.execute(
            insert(comments).values(
                id=comment.id,
                thread_id=comment.thread_id,
                author_id=comment.author_id,
                is_root=comment.is_root,
                created_at=comment.created_at,
                **_comment_values(comment),
            )
        )

    def get_comment(self, comment_id: UUID, *, for_update: bool = False) -> Comment:
        """Return the comment with `comment_id`; `for_update` holds its row until commit."""
        query = select(comments).where(comments.c.id == comment_id)
        if for_update:
            query = query.with_for_update()
        row = self._connection.execute(query).one_or_none()
        if row is None:
            raise CommentNotFoundError(comment_id)
        return _comment(row)

    def comment_view(self, comment_id: UUID) -> CommentView:
        """The comment with its author's name."""
        row = self._connection.execute(
            _comment_query().where(comments.c.id == comment_id)
        ).one_or_none()
        if row is None:
            raise CommentNotFoundError(comment_id)
        return _comment_view(row)

    def replies_page(self, thread_id: UUID, *, cursor: str | None, limit: int) -> Page[CommentView]:
        """Keyset pagination on `(created_at, id)`, oldest first, without the first comment."""
        size = _size(limit)
        query = (
            _comment_query()
            .where(comments.c.thread_id == thread_id, comments.c.is_root.is_(False))
            .order_by(comments.c.created_at, comments.c.id)
        )
        if cursor is not None:
            query = query.where(
                tuple_(comments.c.created_at, comments.c.id) > decode_cursor(cursor)
            )
        rows = self._connection.execute(query.limit(size + 1)).all()
        items = tuple(_comment_view(row) for row in rows[:size])
        last = items[-1].comment if len(rows) > size and items else None
        return Page(
            items=items,
            next_cursor=None if last is None else encode_cursor(last.created_at, last.id),
        )

    def save_comment(self, comment: Comment) -> None:
        """Write an edit or a soft delete."""
        self._connection.execute(
            update(comments).where(comments.c.id == comment.id).values(**_comment_values(comment))
        )
