"""Guards of the comment service that the API cannot reach (KILN-10)."""

import pytest

from kiln_api.domain.ids import uuid7
from kiln_api.errors import IdempotencyKeyInUseError
from kiln_api.ports import IdempotentResult
from kiln_api.services.comments import _created_id


def test_a_key_without_a_created_comment_is_never_replayed() -> None:
    """A key that recorded an asset (or nothing yet) cannot replay as a thread or a reply."""
    with pytest.raises(IdempotencyKeyInUseError):
        _created_id(IdempotentResult(asset_id=uuid7(), version_id=uuid7()))


def test_a_key_with_a_created_comment_replays_it() -> None:
    created = uuid7()

    assert _created_id(IdempotentResult(asset_id=None, version_id=None, resource_id=created)) == (
        created
    )
