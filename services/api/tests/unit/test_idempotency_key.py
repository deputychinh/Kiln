import pytest

from kiln_api.domain.idempotency import parse_idempotency_key, request_fingerprint
from kiln_api.errors import InvalidIdempotencyKeyError


@pytest.mark.parametrize(
    ("header", "key"),
    [
        ('"8e03978e-40d5-43e8-bc93-6894a57f9324"', "8e03978e-40d5-43e8-bc93-6894a57f9324"),
        ("8e03978e-40d5-43e8-bc93-6894a57f9324", "8e03978e-40d5-43e8-bc93-6894a57f9324"),
        ('"a \\"quoted\\" key"', 'a "quoted" key'),
        ('"back\\\\slash"', "back\\slash"),
        ('"' + "k" * 255 + '"', "k" * 255),
    ],
)
def test_valid_keys_are_parsed_as_sf_strings_or_bare_tokens(header: str, key: str) -> None:
    assert parse_idempotency_key(header) == key


@pytest.mark.parametrize(
    "header",
    [
        "",
        '""',
        '"',
        '"unterminated',
        '"bad \\x escape"',
        '"trailing"junk',
        "has space",
        "k" * 256,
        '"' + "k" * 256 + '"',
        "ctl\x01",
        '"ctl\x01"',
        "café",
    ],
)
def test_invalid_keys_are_rejected(header: str) -> None:
    with pytest.raises(InvalidIdempotencyKeyError):
        parse_idempotency_key(header)


def test_the_fingerprint_depends_on_operation_and_payload_but_not_key_order() -> None:
    a = request_fingerprint("create_asset", {"name": "Rock", "size_bytes": 1})
    b = request_fingerprint("create_asset", {"size_bytes": 1, "name": "Rock"})
    other_payload = request_fingerprint("create_asset", {"name": "Rock", "size_bytes": 2})
    other_operation = request_fingerprint("add_version:x", {"name": "Rock", "size_bytes": 1})

    assert a == b
    assert len(a) == 32
    assert len({a, other_payload, other_operation}) == 3
