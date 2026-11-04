import base64
from datetime import UTC, datetime
from uuid import UUID

import pytest

from kiln_api.domain.cursor import decode_cursor, encode_cursor
from kiln_api.errors import InvalidCursorError

AT = datetime(2026, 11, 3, 12, 30, tzinfo=UTC)
ID = UUID("01234567-89ab-7000-8000-000000000000")


def test_a_cursor_round_trips_its_position() -> None:
    assert decode_cursor(encode_cursor(AT, ID)) == (AT, ID)


def test_a_cursor_is_opaque_url_safe_text() -> None:
    cursor = encode_cursor(AT, ID)

    assert "|" not in cursor
    assert all(ch.isalnum() or ch in "-_" for ch in cursor)


@pytest.mark.parametrize(
    "cursor",
    ["", "not base64!", "bm8tc2VwYXJhdG9y", "eHx5", "MjAyNi0xMS0wM3xub3QtYS11dWlk", "A" * 129],
)
def test_a_malformed_cursor_is_rejected(cursor: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor)


@pytest.mark.parametrize("junk", ["!!{cursor}", "{cursor}!!", "{cursor} ", "{cursor}+/"])
def test_a_valid_cursor_with_extra_characters_is_rejected(junk: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(junk.format(cursor=encode_cursor(AT, ID)))


def test_a_cursor_without_a_timezone_is_rejected() -> None:
    raw = f"{AT.replace(tzinfo=None).isoformat()}|{ID}".encode()
    tampered = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    with pytest.raises(InvalidCursorError):
        decode_cursor(tampered)
