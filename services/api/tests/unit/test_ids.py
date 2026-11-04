from uuid import UUID

from kiln_api.domain.ids import uuid7


def test_uuid7_has_version_7_and_the_rfc_variant() -> None:
    value = uuid7()

    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_uuid7_puts_the_millisecond_timestamp_in_the_first_48_bits() -> None:
    value = uuid7(timestamp_ms=0x0123_4567_89AB, random_bytes=bytes(10))

    assert value == UUID("01234567-89ab-7000-8000-000000000000")


def test_uuid7_sorts_by_creation_time() -> None:
    earlier = uuid7(timestamp_ms=1_000, random_bytes=b"\xff" * 10)
    later = uuid7(timestamp_ms=1_001, random_bytes=bytes(10))

    assert str(earlier) < str(later)
