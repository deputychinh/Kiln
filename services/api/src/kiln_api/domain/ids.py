"""Time-ordered identifiers (UUID version 7, RFC 9562 §5.7)."""

import os
import time
from uuid import UUID

_TIMESTAMP_MASK = (1 << 48) - 1
_RAND_B_MASK = (1 << 62) - 1
_RANDOM_BYTES = 10


def uuid7(timestamp_ms: int | None = None, random_bytes: bytes | None = None) -> UUID:
    """Return a UUID v7: 48-bit Unix milliseconds, then 74 random bits.

    Args:
        timestamp_ms: Milliseconds since the epoch; the current time when omitted.
        random_bytes: Ten bytes of randomness; `os.urandom` when omitted.

    Returns:
        A UUID whose string form sorts by creation time.
    """
    millis = time.time_ns() // 1_000_000 if timestamp_ms is None else timestamp_ms
    entropy = int.from_bytes(random_bytes or os.urandom(_RANDOM_BYTES), "big")
    rand_a = entropy >> 68
    rand_b = entropy & _RAND_B_MASK
    value = (millis & _TIMESTAMP_MASK) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return UUID(int=value)
