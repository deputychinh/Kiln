"""Postgres adapter for the `AssetRepository` port."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, Row, func, insert, select, tuple_, update

from kiln_api.constants import PAGE_LIMIT_MAX, PAGE_LIMIT_MIN
from kiln_api.db.schema import asset_versions, assets
from kiln_api.domain.assets import Asset, AssetVersion
from kiln_api.domain.cursor import decode_cursor, encode_cursor
from kiln_api.enums import AssetKind, VersionStatus
from kiln_api.errors import AssetNotFoundError, AssetVersionNotFoundError
from kiln_api.ports import Page


def _asset(row: Row[Any]) -> Asset:
    return Asset(
        id=row.id,
        name=row.name,
        kind=AssetKind(row.kind),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _version(row: Row[Any]) -> AssetVersion:
    return AssetVersion(
        id=row.id,
        asset_id=row.asset_id,
        number=row.number,
        status=VersionStatus(row.status),
        file_name=row.file_name,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        object_key=row.object_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _version_values(version: AssetVersion) -> dict[str, object]:
    return {
        "id": version.id,
        "asset_id": version.asset_id,
        "number": version.number,
        "status": version.status.value,
        "file_name": version.file_name,
        "content_type": version.content_type,
        "size_bytes": version.size_bytes,
        "object_key": version.object_key,
        "created_at": version.created_at,
        "updated_at": version.updated_at,
    }


class SqlAssetRepository:
    """Stores assets in Postgres; each method is one transaction."""

    def __init__(self, engine: Engine) -> None:
        """Use `engine` for every transaction."""
        self._engine = engine

    def add(self, asset: Asset, first_version: AssetVersion) -> None:
        """Insert the asset and its first version together."""
        with self._engine.begin() as connection:
            connection.execute(
                insert(assets).values(
                    id=asset.id,
                    name=asset.name,
                    kind=asset.kind.value,
                    created_at=asset.created_at,
                    updated_at=asset.updated_at,
                )
            )
            connection.execute(insert(asset_versions).values(**_version_values(first_version)))

    def get(self, asset_id: UUID) -> Asset:
        """Return the asset with `asset_id`."""
        with self._engine.connect() as connection:
            row = connection.execute(select(assets).where(assets.c.id == asset_id)).one_or_none()
        if row is None:
            raise AssetNotFoundError(asset_id)
        return _asset(row)

    def list_page(self, *, cursor: str | None, limit: int) -> Page[Asset]:
        """Keyset pagination on `(created_at, id)`, newest first; no OFFSET, no COUNT."""
        size = max(PAGE_LIMIT_MIN, min(PAGE_LIMIT_MAX, limit))
        query = select(assets).order_by(assets.c.created_at.desc(), assets.c.id.desc())
        if cursor is not None:
            created_at, asset_id = decode_cursor(cursor)
            query = query.where(tuple_(assets.c.created_at, assets.c.id) < (created_at, asset_id))
        with self._engine.connect() as connection:
            rows = connection.execute(query.limit(size + 1)).all()
        items = tuple(_asset(row) for row in rows[:size])
        has_more = len(rows) > size
        next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_more else None
        return Page(items=items, next_cursor=next_cursor)

    def add_next_version(
        self, asset_id: UUID, build: Callable[[Asset, int], AssetVersion]
    ) -> AssetVersion:
        """Serialise writers on the asset row so numbers never repeat."""
        with self._engine.begin() as connection:
            row = connection.execute(
                select(assets).where(assets.c.id == asset_id).with_for_update()
            ).one_or_none()
            if row is None:
                raise AssetNotFoundError(asset_id)
            last = connection.execute(
                select(func.coalesce(func.max(asset_versions.c.number), 0)).where(
                    asset_versions.c.asset_id == asset_id
                )
            ).scalar_one()
            version = build(_asset(row), int(last) + 1)
            connection.execute(insert(asset_versions).values(**_version_values(version)))
            connection.execute(
                update(assets).where(assets.c.id == asset_id).values(updated_at=version.created_at)
            )
        return version

    def get_version(self, version_id: UUID) -> AssetVersion:
        """Return the version with `version_id`."""
        with self._engine.connect() as connection:
            row = connection.execute(
                select(asset_versions).where(asset_versions.c.id == version_id)
            ).one_or_none()
        if row is None:
            raise AssetVersionNotFoundError(version_id)
        return _version(row)

    def versions_of(self, asset_id: UUID) -> list[AssetVersion]:
        """Return the versions of `asset_id` in number order."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(asset_versions)
                .where(asset_versions.c.asset_id == asset_id)
                .order_by(asset_versions.c.number)
            ).all()
        return [_version(row) for row in rows]

    def save_version(self, version: AssetVersion) -> None:
        """Write the version's status and timestamp."""
        with self._engine.begin() as connection:
            result = connection.execute(
                update(asset_versions)
                .where(asset_versions.c.id == version.id)
                .values(status=version.status.value, updated_at=version.updated_at)
            )
        if result.rowcount == 0:
            raise AssetVersionNotFoundError(version.id)
