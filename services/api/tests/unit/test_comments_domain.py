"""Comment and region rules (KILN-10)."""

import math
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import UUID, uuid4

import pytest

from kiln_api.constants import COMMENT_BODY_MAX_LENGTH
from kiln_api.domain.comments import (
    Region,
    check_region,
    clean_comment_body,
    delete_comment,
    edit_comment,
    new_reply,
    new_thread,
    set_resolved,
)
from kiln_api.enums import RegionShape
from kiln_api.errors import CommentDeletedError, InvalidCommentBodyError, InvalidRegionError

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
AUTHOR = uuid4()
_SEQUENCE = count(1)


def _id() -> UUID:
    return UUID(int=next(_SEQUENCE))


def _rect(x: float, y: float, width: float, height: float) -> Region:
    return Region(shape=RegionShape.RECT, x=x, y=y, width=width, height=height)


def test_the_comment_limit_is_2000_characters() -> None:
    assert COMMENT_BODY_MAX_LENGTH == 2000


@pytest.mark.parametrize("length", [1, 2000])
def test_a_body_of_1_to_2000_characters_is_kept(length: int) -> None:
    assert clean_comment_body("x" * length) == "x" * length


def test_a_body_of_2001_characters_is_refused() -> None:
    with pytest.raises(InvalidCommentBodyError):
        clean_comment_body("x" * 2001)


def test_a_body_is_trimmed_before_it_is_measured() -> None:
    assert clean_comment_body("  " + "x" * 2000 + "\n\n") == "x" * 2000


def test_line_breaks_are_kept_and_unified() -> None:
    assert clean_comment_body("one\r\ntwo\rthree\nfour") == "one\ntwo\nthree\nfour"


@pytest.mark.parametrize(
    "body",
    ["", "\n\n", "\x7f", "a\tb", "a\x1bb", "a\u200bb", "a\u2066b", "\u2800", "a\ud800b", "a\x85b"],
)
def test_hidden_and_control_characters_other_than_line_breaks_are_refused(body: str) -> None:
    with pytest.raises(InvalidCommentBodyError):
        clean_comment_body(body)


@pytest.mark.parametrize(
    ("x", "y", "width", "height"),
    [(0, 0, 1, 1), (0.5, 0.5, 0.5, 0.5), (0.99, 0, 0.01, 1), (0.3, 0.3, 0.01, 0.01)],
)
def test_a_rectangle_inside_the_image_is_valid(
    x: float, y: float, width: float, height: float
) -> None:
    region = _rect(x, y, width, height)

    assert check_region(region) is region


@pytest.mark.parametrize(
    ("x", "y", "width", "height"),
    [
        (-1e-9, 0, 0.5, 0.5),
        (0, -1e-9, 0.5, 0.5),
        (0.5, 0, 0.5000001, 0.5),
        (0, 0.5, 0.5, 0.5000001),
        (0, 0, 0, 0.5),
        (0, 0, 0.5, 0),
        (0, 0, -0.5, 0.5),
        (math.nan, 0, 0.5, 0.5),
        (0, 0, math.inf, 0.5),
        (0, 0, 0.5, math.nan),
        (0, 0, 0.0099, 0.5),
        (0, 0, 0.5, 1e-300),
    ],
)
def test_a_rectangle_past_an_edge_or_without_size_is_refused(
    x: float, y: float, width: float, height: float
) -> None:
    with pytest.raises(InvalidRegionError):
        check_region(_rect(x, y, width, height))


def test_a_rectangle_needs_both_sizes() -> None:
    with pytest.raises(InvalidRegionError):
        check_region(Region(shape=RegionShape.RECT, x=0, y=0, width=0.5))


@pytest.mark.parametrize(("x", "y"), [(0, 0), (1, 1), (0.5, 0.25)])
def test_a_point_anywhere_on_the_image_is_valid(x: float, y: float) -> None:
    assert check_region(Region(shape=RegionShape.POINT, x=x, y=y)).x == x


@pytest.mark.parametrize(
    "region",
    [
        Region(shape=RegionShape.POINT, x=1.0000001, y=0.5),
        Region(shape=RegionShape.POINT, x=0.5, y=-0.1),
        Region(shape=RegionShape.POINT, x=math.nan, y=0.5),
        Region(shape=RegionShape.POINT, x=0.5, y=0.5, width=0.1),
        Region(shape=RegionShape.POINT, x=0.5, y=0.5, height=0.1),
    ],
)
def test_a_point_off_the_image_or_with_a_size_is_refused(region: Region) -> None:
    with pytest.raises(InvalidRegionError):
        check_region(region)


def test_a_new_thread_has_its_first_comment_and_waits_for_a_number() -> None:
    version_id = uuid4()

    thread, root = new_thread(
        version_id, author_id=AUTHOR, body=" Hi ", region=None, now=NOW, new_id=_id
    )

    assert (thread.version_id, thread.number, thread.region) == (version_id, 0, None)
    assert (root.thread_id, root.body, root.is_root, root.author_id) == (
        thread.id,
        "Hi",
        True,
        AUTHOR,
    )


def test_a_new_thread_checks_its_region() -> None:
    with pytest.raises(InvalidRegionError):
        new_thread(
            uuid4(),
            author_id=AUTHOR,
            body="Hi",
            region=_rect(0.9, 0, 0.2, 0.2),
            now=NOW,
            new_id=_id,
        )


def test_a_reply_is_not_a_root() -> None:
    thread, _ = new_thread(uuid4(), author_id=AUTHOR, body="Hi", region=None, now=NOW, new_id=_id)

    reply = new_reply(thread, author_id=AUTHOR, body="Yes", now=NOW, new_id=_id)

    assert (reply.thread_id, reply.is_root, reply.body) == (thread.id, False, "Yes")


def test_editing_marks_the_comment_edited_and_a_deleted_one_cannot_be_edited() -> None:
    _, root = new_thread(uuid4(), author_id=AUTHOR, body="Hi", region=None, now=NOW, new_id=_id)
    later = NOW + timedelta(minutes=1)

    edited = edit_comment(root, "Hello", now=later)
    deleted = delete_comment(edited, now=later)

    assert (edited.body, edited.edited_at) == ("Hello", later)
    assert (deleted.body, deleted.deleted_at, deleted.is_deleted) == ("", later, True)
    assert delete_comment(deleted, now=later + timedelta(minutes=1)) is deleted
    with pytest.raises(CommentDeletedError):
        edit_comment(deleted, "Back", now=later)


def test_resolving_keeps_the_first_resolution_and_reopening_clears_it() -> None:
    thread, _ = new_thread(uuid4(), author_id=AUTHOR, body="Hi", region=None, now=NOW, new_id=_id)
    first, second = uuid4(), uuid4()
    later = NOW + timedelta(minutes=1)

    resolved = set_resolved(thread, resolved=True, by=first, now=later)
    again = set_resolved(resolved, resolved=True, by=second, now=later + timedelta(minutes=1))
    reopened = set_resolved(again, resolved=False, by=second, now=later)

    assert (resolved.resolved_at, resolved.resolved_by, resolved.updated_at) == (
        later,
        first,
        later,
    )
    assert again is resolved
    assert (reopened.resolved_at, reopened.resolved_by) == (None, None)
    assert set_resolved(reopened, resolved=False, by=first, now=later) is reopened
