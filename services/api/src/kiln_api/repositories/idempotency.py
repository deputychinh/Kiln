"""Postgres adapter for the `IdempotencyStore` port and the expiry purge."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, Row, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError

from kiln_api.constants import IDEMPOTENCY_WINDOW_HOURS, LOCK_NOT_AVAILABLE_SQLSTATE
from kiln_api.db.schema import idempotency_keys
from kiln_api.errors import IdempotencyKeyInUseError, IdempotencyKeyReusedError
from kiln_api.ports import IdempotentResult

_WINDOW = timedelta(hours=IDEMPOTENCY_WINDOW_HOURS)


class SqlIdempotencyStore:
    """Keys live in the caller's transaction, so the key and the created rows commit together."""

    def __init__(self, connection: Connection) -> None:
        """Join the transaction of `connection`."""
        self._connection = connection

    def claim(
        self, *, key: str, operation: str, request_hash: bytes, now: datetime
    ) -> IdempotentResult | None:
        """Return the stored result of a completed request, or None after claiming the key.

        A concurrent claim of the same key waits on the uncommitted row; a wait longer than
        `lock_timeout` becomes `IdempotencyKeyInUseError`.
        """
        try:
            row = self._claim_or_read(key, operation, request_hash, now)
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE_SQLSTATE:
                raise IdempotencyKeyInUseError from error
            raise
        if row is None:
            return None
        if row.request_hash != request_hash:
            raise IdempotencyKeyReusedError
        return IdempotentResult(asset_id=row.asset_id, version_id=row.version_id)

    def _claim_or_read(
        self, key: str, operation: str, request_hash: bytes, now: datetime
    ) -> Row[Any] | None:
        self._connection.execute(
            delete(idempotency_keys).where(
                idempotency_keys.c.key == key, idempotency_keys.c.created_at < now - _WINDOW
            )
        )
        claimed = self._connection.execute(
            insert(idempotency_keys)
            .values(key=key, operation=operation, request_hash=request_hash, created_at=now)
            .on_conflict_do_nothing(index_elements=[idempotency_keys.c.key])
            .returning(idempotency_keys.c.key)
        ).first()
        if claimed is not None:
            return None
        return self._connection.execute(
            select(idempotency_keys).where(idempotency_keys.c.key == key)
        ).one()

    def complete(self, *, key: str, asset_id: UUID, version_id: UUID) -> None:
        """Record what the request created, in the same transaction."""
        self._connection.execute(
            update(idempotency_keys)
            .where(idempotency_keys.c.key == key)
            .values(asset_id=asset_id, version_id=version_id)
        )


def purge_expired_keys(engine: Engine, *, now: datetime | None = None, limit: int) -> int:
    """Delete up to `limit` keys older than the window (oldest first); scheduled by the worker.

    `now` defaults to the database clock; tests pass a fixed one.
    """
    cutoff = (func.now() if now is None else now) - _WINDOW
    expired = (
        select(idempotency_keys.c.key)
        .where(idempotency_keys.c.created_at < cutoff)
        .order_by(idempotency_keys.c.created_at)
        .limit(limit)
    )
    with engine.begin() as connection:
        result = connection.execute(
            delete(idempotency_keys).where(idempotency_keys.c.key.in_(expired.scalar_subquery()))
        )
    return result.rowcount
