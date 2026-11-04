"""Opaque keyset cursors for newest-first lists (Zalando guideline 160)."""

import base64
import binascii
from datetime import datetime
from uuid import UUID

from kiln_api.errors import InvalidCursorError

_SEPARATOR = "|"


def encode_cursor(created_at: datetime, item_id: UUID) -> str:
    """Encode the position after which the next page starts."""
    raw = f"{created_at.isoformat()}{_SEPARATOR}{item_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode a cursor from `encode_cursor`.

    Raises:
        InvalidCursorError: The cursor was not produced by this API.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_text, id_text = raw.split(_SEPARATOR)
        created_at = datetime.fromisoformat(created_text)
        item_id = UUID(id_text)
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise InvalidCursorError from error
    if created_at.tzinfo is None:
        raise InvalidCursorError
    return created_at, item_id
