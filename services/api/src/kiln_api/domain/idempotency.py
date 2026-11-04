"""Idempotency keys: header syntax (RFC 9651 sf-string) and request fingerprints."""

import hashlib
import json
import re

from kiln_api.constants import IDEMPOTENCY_KEY_MAX_LENGTH
from kiln_api.errors import InvalidIdempotencyKeyError

# A bare token is tolerated as well as the sf-string the draft specifies.
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z:/]+")
_SF_STRING = re.compile(r'"((?:[\x20\x21\x23-\x5b\x5d-\x7e]|\\["\\])*)"')


def parse_idempotency_key(header: str) -> str:
    """Return the key from an `Idempotency-Key` header value.

    Raises:
        InvalidIdempotencyKeyError: Not an sf-string or token of 1 to 255 printable characters.
    """
    quoted = _SF_STRING.fullmatch(header)
    if quoted is not None:
        key = re.sub(r"\\(.)", r"\1", quoted.group(1))
    elif _TOKEN.fullmatch(header):
        key = header
    else:
        raise InvalidIdempotencyKeyError
    if not 1 <= len(key) <= IDEMPOTENCY_KEY_MAX_LENGTH:
        raise InvalidIdempotencyKeyError
    return key


def request_fingerprint(operation: str, payload: dict[str, object]) -> bytes:
    """SHA-256 of the operation and the canonical JSON payload (key order does not matter)."""
    canonical = json.dumps(
        {"operation": operation, "payload": payload}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).digest()
