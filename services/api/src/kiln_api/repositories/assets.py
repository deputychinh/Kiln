"""Postgres adapter for the `AssetRepository` port."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, Row, func, insert, or_, select, tuple_, update

from kiln_api.constants import (
    ALLOWED_TRANSITIONS,
    MAX_VERSIONS_PER_READ,
    PAGE_LIMIT_MAX,
    PAGE_LIMIT_MIN,
)
from kiln_api.db.schema import asset_versions, assets
from kiln_api.domain.assets import Asset, AssetVersion
from kiln_api.domain.cursor import decode_cursor, encode_cursor
from kiln_api.enums import AssetKind, FailureReason, VersionStatus
from kiln_api.errors import (
    AssetNotFoundError,
    AssetVersionNotFoundError,
    InvalidStatusTransitionError,
)
from kiln_api.ports import Page


def _asset(row: Row[Any]) -> Asset:
    return Asset(
        id=row.id,
        name=row.name,
        kind=AssetKind(row.kind),
        created_at=row.created_at,
        updated_at=row.updated_at,
        cover_version_id=row.cover_version_id,
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
        etag=row.etag,
        failure_reason=None if row.failure_reason is None else FailureReason(row.failure_reason),
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
        "etag": version.etag,
        "failure_reason": None if version.failure_reason is None else version.failure_reason.value,
    }


class SqlAssetRepository:
    """Stores assets in Postgres.

    Bound to an `Engine`, each method is its own transaction; bound to a `Connection` (inside a
    unit of work), every method joins the caller's transaction.
    """

    def __init__(self, bind: Engine | Connection) -> None:
        """Use `bind` for every statement."""
        self._bind = bind

    @contextmanager
    def _write(self) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            yield self._bind
        else:
            with self._bind.begin() as connection:
                yield connection

    @contextmanager
    def _read(self) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            yield self._bind
        else:
            with self._bind.connect() as connection:
                yield connection

    def add(self, asset: Asset, first_version: AssetVersion) -> None:
        """Insert the asset and its first version together."""
        with self._write() as connection:
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
        with self._read() as connection:
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
        with self._read() as connection:
            rows = connection.execute(query.limit(size + 1)).all()
        items = tuple(_asset(row) for row in rows[:size])
        has_more = len(rows) > size
        next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_more else None
        return Page(items=items, next_cursor=next_cursor)

    def add_next_version(
        self, asset_id: UUID, build: Callable[[Asset, int], AssetVersion]
    ) -> AssetVersion:
        """Serialise writers on the asset row so numbers never repeat."""
        with self._write() as connection:
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
                update(assets)
                .where(assets.c.id == asset_id)
                .values(updated_at=func.greatest(assets.c.updated_at, version.created_at))
            )
        return version

    def get_version(self, version_id: UUID) -> AssetVersion:
        """Return the version with `version_id`."""
        with self._read() as connection:
            row = connection.execute(
                select(asset_versions).where(asset_versions.c.id == version_id)
            ).one_or_none()
        if row is None:
            raise AssetVersionNotFoundError(version_id)
        return _version(row)

    def versions_by_id(self, version_ids: Sequence[UUID]) -> dict[UUID, AssetVersion]:
        """The versions among `version_ids` that exist, in one query."""
        with self._read() as connection:
            rows = connection.execute(
                select(asset_versions).where(asset_versions.c.id.in_(version_ids))
            ).all()
        return {row.id: _version(row) for row in rows}

    def versions_of(self, asset_id: UUID) -> list[AssetVersion]:
        """Return the versions of `asset_id` in number order, at most `MAX_VERSIONS_PER_READ`."""
        with self._read() as connection:
            rows = connection.execute(
                select(asset_versions)
                .where(asset_versions.c.asset_id == asset_id)
                .order_by(asset_versions.c.number)
                .limit(MAX_VERSIONS_PER_READ)
            ).all()
        return [_version(row) for row in rows]

    def save_version(self, version: AssetVersion, *, expected: VersionStatus) -> None:
        """Write the new status only if the stored one is still `expected` (compare-and-set)."""
        if version.status not in ALLOWED_TRANSITIONS[expected]:
            raise InvalidStatusTransitionError(expected, version.status)
        with self._write() as connection:
            result = connection.execute(
                update(asset_versions)
                .where(asset_versions.c.id == version.id, asset_versions.c.status == expected.value)
                .values(
                    status=version.status.value,
                    updated_at=version.updated_at,
                    etag=version.etag,
                    failure_reason=(
                        None if version.failure_reason is None else version.failure_reason.value
                    ),
                )
            )
            if result.rowcount == 1:
                return
            current = connection.execute(
                select(asset_versions.c.status).where(asset_versions.c.id == version.id)
            ).scalar_one_or_none()
        if current is None:
            raise AssetVersionNotFoundError(version.id)
        raise InvalidStatusTransitionError(VersionStatus(current), version.status)

    def promote_cover(self, version: AssetVersion) -> None:
        """Make `version` the asset's cover unless a newer version already is."""
        newer_cover = (
            select(asset_versions.c.number)
            .where(asset_versions.c.id == assets.c.cover_version_id)
            .scalar_subquery()
        )
        with self._write() as connection:
            connection.execute(
                update(assets)
                .where(
                    assets.c.id == version.asset_id,
                    or_(assets.c.cover_version_id.is_(None), newer_cover < version.number),
                )
                .values(cover_version_id=version.id)
            )

    def drop_cover(self, version: AssetVersion) -> None:
        """If `version` is the cover, the newest other ready version takes its place (or none).

        The asset row is locked first, so the fallback is chosen from a snapshot taken after any
        other writer of this asset's cover committed: two versions failed at once never leave a
        failed cover, and a newer version a worker makes ready meanwhile still becomes the cover.
        """
        fallback = (
            select(asset_versions.c.id)
            .where(
                asset_versions.c.asset_id == version.asset_id,
                asset_versions.c.status == VersionStatus.READY.value,
                asset_versions.c.id != version.id,
            )
            .order_by(asset_versions.c.number.desc())
            .limit(1)
            .scalar_subquery()
        )
        with self._write() as connection:
            connection.execute(
                select(assets.c.id).where(assets.c.id == version.asset_id).with_for_update()
            )
            connection.execute(
                update(assets)
                .where(assets.c.id == version.asset_id, assets.c.cover_version_id == version.id)
                .values(cover_version_id=fallback)
            )
