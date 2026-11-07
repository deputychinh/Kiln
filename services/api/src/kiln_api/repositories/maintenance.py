"""Postgres side of maintenance: the run lease, stale uploads (KILN-22), ready models (KILN-36)."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert

from kiln_api.db.schema import asset_versions, assets, maintenance_runs
from kiln_api.enums import AssetKind, VersionStatus


class SqlMaintenanceStore:
    """Decides on the database clock, so every worker agrees whatever its own clock says."""

    def __init__(self, engine: Engine) -> None:
        """Use `engine` for short transactions of their own."""
        self._engine = engine

    def try_start(self, task: str, *, every: timedelta, now: datetime | None = None) -> bool:
        """Take the run of `task` if none started within `every`; one statement, so one winner.

        `now` defaults to the database clock; tests pass a fixed one.
        """
        current = func.now() if now is None else now
        statement = (
            insert(maintenance_runs)
            .values(task=task, last_started_at=current)
            .on_conflict_do_update(
                index_elements=[maintenance_runs.c.task],
                set_={"last_started_at": current},
                where=maintenance_runs.c.last_started_at <= current - every,
            )
            .returning(maintenance_runs.c.task)
        )
        with self._engine.begin() as connection:
            return connection.execute(statement).first() is not None

    def stale_pending_versions(
        self, *, older_than: timedelta, limit: int, now: datetime | None = None
    ) -> list[UUID]:
        """Ids of versions still waiting for their upload after `older_than`, oldest first."""
        current = func.now() if now is None else now
        query = (
            select(asset_versions.c.id)
            .where(
                asset_versions.c.status == VersionStatus.PENDING_UPLOAD.value,
                asset_versions.c.created_at < current - older_than,
            )
            .order_by(asset_versions.c.created_at)
            .limit(limit)
        )
        with self._engine.connect() as connection:
            return list(connection.execute(query).scalars())

    def ready_model_versions(self, *, after: UUID | None, limit: int) -> list[UUID]:
        """Ids of ready versions of model assets after `after`, in id order (keyset pages).

        A one-off re-check walks them all; the primary key orders the walk, so versions failed
        by the walk itself never shift a page.
        """
        query = (
            select(asset_versions.c.id)
            .join(assets, assets.c.id == asset_versions.c.asset_id)
            .where(
                asset_versions.c.status == VersionStatus.READY.value,
                assets.c.kind == AssetKind.MODEL.value,
            )
            .order_by(asset_versions.c.id)
            .limit(limit)
        )
        if after is not None:
            query = query.where(asset_versions.c.id > after)
        with self._engine.connect() as connection:
            return list(connection.execute(query).scalars())
