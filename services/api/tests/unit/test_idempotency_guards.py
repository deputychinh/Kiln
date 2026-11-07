from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest
from fakes import FakeStorage, FixedClock
from sqlalchemy.exc import DBAPIError

from kiln_api.domain.assets import UploadSpec
from kiln_api.domain.identity import Principal
from kiln_api.domain.ids import uuid7
from kiln_api.enums import AuthMethod, Scope
from kiln_api.errors import IdempotencyKeyInUseError
from kiln_api.main import create_app
from kiln_api.ports import IdempotentResult
from kiln_api.repositories.idempotency import SqlIdempotencyStore
from kiln_api.services.assets import AssetService

SPEC = UploadSpec(file_name="a.png", content_type="image/png", size_bytes=1)
PRINCIPAL = Principal(
    user_id=uuid4(),
    email="ada@kiln.test",
    display_name="Ada",
    method=AuthMethod.SESSION,
    scopes=frozenset(Scope),
)


class _HalfDoneStore:
    def claim(self, **_: object) -> IdempotentResult:
        return IdempotentResult(asset_id=None, version_id=None)

    def complete(self, **_: object) -> None:
        raise AssertionError


class _Tx:
    assets: Any = None
    idempotency = _HalfDoneStore()


@contextmanager
def _uow() -> Iterator[_Tx]:
    yield _Tx()


def test_a_half_recorded_key_is_never_replayed() -> None:
    service = AssetService(None, FakeStorage(), FixedClock(), uuid7, _uow)  # type: ignore[arg-type]

    with pytest.raises(IdempotencyKeyInUseError):
        service.create(PRINCIPAL, "Rock", SPEC, idempotency_key="k")


class _FailingConnection:
    def execute(self, *_: object) -> None:
        orig = type("Orig", (Exception,), {"sqlstate": "XX000"})()
        raise DBAPIError("DELETE", {}, orig)


def test_other_database_errors_during_a_claim_propagate() -> None:
    store = SqlIdempotencyStore(_FailingConnection())  # type: ignore[arg-type]

    with pytest.raises(DBAPIError):
        store.claim(
            user_id=uuid4(),
            key=str(uuid4()),
            operation="create_asset",
            request_hash=b"\0" * 32,
            now=FixedClock().now(),
        )


def test_the_openapi_schema_is_built_once() -> None:
    app = create_app()

    assert app.openapi() is app.openapi()
