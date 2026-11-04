import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from kiln_api.domain.assets import (
    Asset,
    AssetVersion,
    UploadSpec,
    new_asset,
    new_version,
    transition,
)
from kiln_api.domain.ids import uuid7
from kiln_api.enums import VersionStatus
from kiln_api.errors import (
    AssetNotFoundError,
    AssetVersionNotFoundError,
    InvalidCursorError,
    InvalidStatusTransitionError,
)
from kiln_api.repositories.assets import SqlAssetRepository

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
PNG = UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=2048)


def _create(repo: SqlAssetRepository, name: str, at: datetime) -> tuple[Asset, AssetVersion]:
    asset, version = new_asset(name, PNG, now=at, new_id=uuid7)
    repo.add(asset, version)
    return asset, version


def test_an_added_asset_and_its_first_version_can_be_read_back(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    asset, version = _create(repo, "Rock", T0)

    assert repo.get(asset.id) == asset
    assert repo.get_version(version.id) == version
    assert repo.versions_of(asset.id) == [version]


def test_reading_an_unknown_asset_raises_not_found(engine: Engine) -> None:
    with pytest.raises(AssetNotFoundError):
        SqlAssetRepository(engine).get(uuid7())


def test_reading_an_unknown_version_raises_not_found(engine: Engine) -> None:
    with pytest.raises(AssetVersionNotFoundError):
        SqlAssetRepository(engine).get_version(uuid7())


def test_new_versions_take_the_next_number(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    asset, _ = _create(repo, "Rock", T0)

    second = repo.add_next_version(
        asset.id, lambda a, n: new_version(a, n, PNG, now=T0, new_id=uuid7)
    )
    third = repo.add_next_version(
        asset.id, lambda a, n: new_version(a, n, PNG, now=T0, new_id=uuid7)
    )

    assert [v.number for v in repo.versions_of(asset.id)] == [1, 2, 3]
    assert (second.number, third.number) == (2, 3)


def test_adding_a_version_to_an_unknown_asset_raises_not_found(engine: Engine) -> None:
    with pytest.raises(AssetNotFoundError):
        SqlAssetRepository(engine).add_next_version(
            uuid7(), lambda a, n: new_version(a, n, PNG, now=T0, new_id=uuid7)
        )


def test_concurrent_writers_never_get_the_same_version_number(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    asset, _ = _create(repo, "Rock", T0)
    numbers: list[int] = []
    barrier = threading.Barrier(4)

    def add() -> None:
        barrier.wait()
        version = repo.add_next_version(
            asset.id, lambda a, n: new_version(a, n, PNG, now=T0, new_id=uuid7)
        )
        numbers.append(version.number)

    threads = [threading.Thread(target=add) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(numbers) == [2, 3, 4, 5]


def test_a_saved_status_change_is_persisted(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    _, version = _create(repo, "Rock", T0)

    moved = transition(version, VersionStatus.PROCESSING, now=T0 + timedelta(minutes=1))
    repo.save_version(moved, expected=VersionStatus.PENDING_UPLOAD)

    assert repo.get_version(version.id) == moved


def test_saving_an_unknown_version_raises_not_found(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    _, version = new_asset("Rock", PNG, now=T0, new_id=uuid7)
    processing = transition(version, VersionStatus.PROCESSING, now=T0)

    with pytest.raises(AssetVersionNotFoundError):
        repo.save_version(processing, expected=VersionStatus.PENDING_UPLOAD)


def test_pages_are_newest_first_without_gaps_or_overlap(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    created = [_create(repo, f"Asset {i}", T0 + timedelta(seconds=i))[0] for i in range(25)]

    seen: list[UUID] = []
    cursor: str | None = None
    pages = 0
    while True:
        page = repo.list_page(cursor=cursor, limit=10)
        seen.extend(asset.id for asset in page.items)
        pages += 1
        cursor = page.next_cursor
        if cursor is None:
            break

    assert pages == 3
    assert seen == [asset.id for asset in reversed(created)]


def test_assets_created_in_the_same_instant_are_still_paged_exactly_once(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    created = {_create(repo, f"Asset {i}", T0)[0].id for i in range(5)}

    first = repo.list_page(cursor=None, limit=2)
    second = repo.list_page(cursor=first.next_cursor, limit=2)
    third = repo.list_page(cursor=second.next_cursor, limit=2)

    ids = [a.id for a in (*first.items, *second.items, *third.items)]
    assert sorted(ids) == sorted(created)
    assert third.next_cursor is None


def test_an_exactly_full_last_page_has_no_next_cursor(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    for i in range(4):
        _create(repo, f"Asset {i}", T0 + timedelta(seconds=i))

    page = repo.list_page(cursor=None, limit=4)

    assert len(page.items) == 4
    assert page.next_cursor is None


def test_an_empty_database_gives_an_empty_page(engine: Engine) -> None:
    page = SqlAssetRepository(engine).list_page(cursor=None, limit=10)

    assert page.items == ()
    assert page.next_cursor is None


@pytest.mark.parametrize(("asked", "returned"), [(0, 1), (-5, 1), (500, 100)])
def test_the_page_limit_is_clamped(engine: Engine, asked: int, returned: int) -> None:
    repo = SqlAssetRepository(engine)
    for i in range(101):
        _create(repo, f"Asset {i}", T0 + timedelta(seconds=i))

    assert len(repo.list_page(cursor=None, limit=asked).items) == returned


def test_a_malformed_cursor_is_rejected(engine: Engine) -> None:
    with pytest.raises(InvalidCursorError):
        SqlAssetRepository(engine).list_page(cursor="nope", limit=10)


def test_the_database_rejects_a_duplicate_version_number(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    asset, version = _create(repo, "Rock", T0)
    duplicate = new_version(asset, 1, PNG, now=T0, new_id=uuid7)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO asset_versions (id, asset_id, number, status, file_name, content_type,"
                " size_bytes, object_key, created_at, updated_at) VALUES (:id, :asset_id, 1,"
                " 'pending_upload', 'a.png', 'image/png', 1, :key, now(), now())"
            ),
            {"id": duplicate.id, "asset_id": asset.id, "key": duplicate.object_key},
        )
    assert version.number == 1


@pytest.mark.parametrize(
    ("column", "value"),
    [("status", "'archived'"), ("size_bytes", "0"), ("number", "0"), ("file_name", "''")],
)
def test_the_database_enforces_version_invariants(engine: Engine, column: str, value: str) -> None:
    repo = SqlAssetRepository(engine)
    _, version = _create(repo, "Rock", T0)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(f"UPDATE asset_versions SET {column} = {value} WHERE id = :id"),  # noqa: S608 - fixed test values
            {"id": version.id},
        )


def test_a_stale_status_change_is_rejected_instead_of_overwriting(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    _, version = _create(repo, "Rock", T0)
    processing = transition(version, VersionStatus.PROCESSING, now=T0)
    repo.save_version(processing, expected=VersionStatus.PENDING_UPLOAD)
    ready = transition(processing, VersionStatus.READY, now=T0)
    failed = transition(processing, VersionStatus.FAILED, now=T0)

    repo.save_version(ready, expected=VersionStatus.PROCESSING)
    with pytest.raises(InvalidStatusTransitionError):
        repo.save_version(failed, expected=VersionStatus.PROCESSING)

    assert repo.get_version(version.id).status is VersionStatus.READY


def test_concurrent_status_changes_let_exactly_one_writer_win(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    _, version = _create(repo, "Rock", T0)
    processing = transition(version, VersionStatus.PROCESSING, now=T0)
    repo.save_version(processing, expected=VersionStatus.PENDING_UPLOAD)
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def finish(target: VersionStatus) -> None:
        barrier.wait()
        try:
            repo.save_version(
                transition(processing, target, now=T0), expected=VersionStatus.PROCESSING
            )
            outcomes.append("won")
        except InvalidStatusTransitionError:
            outcomes.append("lost")

    threads = [
        threading.Thread(target=finish, args=(status,))
        for status in (VersionStatus.READY, VersionStatus.FAILED)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["lost", "won"]


@pytest.mark.parametrize(
    ("column", "value"),
    [("name", "''"), ("name", "repeat('x', 121)"), ("kind", "'video'")],
)
def test_the_database_enforces_asset_invariants(engine: Engine, column: str, value: str) -> None:
    repo = SqlAssetRepository(engine)
    asset, _ = _create(repo, "Rock", T0)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(f"UPDATE assets SET {column} = {value} WHERE id = :id"),  # noqa: S608 - fixed test values
            {"id": asset.id},
        )


def test_an_expected_status_that_skips_the_life_cycle_is_rejected(engine: Engine) -> None:
    repo = SqlAssetRepository(engine)
    _, version = _create(repo, "Rock", T0)
    processing = transition(version, VersionStatus.PROCESSING, now=T0)
    ready = transition(processing, VersionStatus.READY, now=T0)

    with pytest.raises(InvalidStatusTransitionError):
        repo.save_version(ready, expected=VersionStatus.PENDING_UPLOAD)

    assert repo.get_version(version.id).status is VersionStatus.PENDING_UPLOAD
