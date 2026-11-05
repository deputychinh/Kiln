"""One Postgres transaction shared by several repositories."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine

from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.idempotency import SqlIdempotencyStore
from kiln_api.repositories.jobs import SqlJobQueue


@dataclass(frozen=True, slots=True)
class SqlTransaction:
    """Repositories bound to the same connection."""

    assets: SqlAssetRepository
    idempotency: SqlIdempotencyStore
    jobs: SqlJobQueue


class SqlUnitOfWork:
    """`with uow() as tx:` commits on success and rolls back on any exception."""

    def __init__(self, engine: Engine) -> None:
        """Open transactions on `engine`."""
        self._engine = engine

    @contextmanager
    def __call__(self) -> Iterator[SqlTransaction]:
        """Start a transaction and hand out repositories bound to it."""
        with self._engine.begin() as connection:
            yield SqlTransaction(
                assets=SqlAssetRepository(connection),
                idempotency=SqlIdempotencyStore(connection),
                jobs=SqlJobQueue(connection),
            )
