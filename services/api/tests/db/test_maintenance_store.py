import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fakes import FakeStorage, FixedClock
from sqlalchemy import Engine

from kiln_api.config import Settings
from kiln_api.container import build_container
from kiln_api.domain.assets import AssetVersion, UploadSpec, new_asset, new_version, transition
from kiln_api.domain.ids import uuid7
from kiln_api.enums import Environment, FailureReason, VersionStatus
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.maintenance import SqlMaintenanceStore

T0 = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
GLB = UploadSpec(file_name="crate.glb", content_type="model/gltf-binary", size_bytes=2048)
PNG = UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=2048)


def test_a_run_starts_once_per_interval(engine: Engine) -> None:
    store = SqlMaintenanceStore(engine)

    assert store.try_start("cleanup", every=HOUR, now=T0) is True
    assert (
        store.try_start("cleanup", every=HOUR, now=T0 + HOUR - timedelta(microseconds=1)) is False
    )
    assert store.try_start("other", every=HOUR, now=T0) is True
    assert store.try_start("cleanup", every=HOUR, now=T0 + HOUR) is True


def test_concurrent_workers_get_exactly_one_run(engine: Engine) -> None:
    store = SqlMaintenanceStore(engine)
    barrier = threading.Barrier(8)
    results: list[bool] = []

    def contend() -> None:
        barrier.wait()
        results.append(store.try_start("cleanup", every=HOUR))  # the database clock

    threads = [threading.Thread(target=contend) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [False] * 7 + [True]


def test_stale_pending_versions_are_found_oldest_first_and_bounded(
    database_url: str, engine: Engine
) -> None:
    clock = FixedClock(T0)
    storage = FakeStorage()
    container = build_container(
        Settings(env=Environment.TEST, database_url=database_url),
        engine=engine,
        storage=storage,
        clock=clock,
    )
    spec = UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=10)
    first = container.assets.create("First", spec).version
    clock.advance(60)
    second = container.assets.create("Second", spec).version
    clock.advance(60)
    completed = container.assets.create("Done", spec)
    storage.put(completed.upload.fields["key"] if completed.upload else "", 10, "image/png")
    container.assets.complete_upload(completed.version.id)
    store = SqlMaintenanceStore(engine)
    day = timedelta(hours=24)

    at_24h_of_first = T0 + day
    assert store.stale_pending_versions(older_than=day, limit=10, now=at_24h_of_first) == []
    later = T0 + day + timedelta(minutes=5)
    assert store.stale_pending_versions(older_than=day, limit=10, now=later) == [
        first.id,
        second.id,
    ]
    assert store.stale_pending_versions(older_than=day, limit=1, now=later) == [first.id]


def test_versions_are_looked_up_by_id_in_one_query(database_url: str, engine: Engine) -> None:
    container = build_container(
        Settings(env=Environment.TEST, database_url=database_url),
        engine=engine,
        storage=FakeStorage(),
        clock=FixedClock(T0),
    )
    spec = UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=10)
    first = container.assets.create("First", spec).version
    second = container.assets.create("Second", spec).version
    repository = SqlAssetRepository(engine)

    found = repository.versions_by_id([first.id, second.id, uuid4()])

    assert found == {first.id: first, second.id: second}
    assert repository.versions_by_id([]) == {}


def _model_in(
    repository: SqlAssetRepository,
    status: VersionStatus,
    *,
    spec: UploadSpec = GLB,
    asset_id: UUID | None = None,
) -> AssetVersion:
    """A version of a new asset (or of `asset_id`) moved to `status`, stored."""
    if asset_id is None:
        asset, version = new_asset("Crate", spec, now=T0, new_id=uuid7)
        repository.add(asset, version)
    else:
        version = repository.add_next_version(
            asset_id, lambda a, n: new_version(a, n, spec, now=T0, new_id=uuid7)
        )
    if status is VersionStatus.PENDING_UPLOAD:
        return version
    processing = transition(version, VersionStatus.PROCESSING, now=T0)
    repository.save_version(processing, expected=VersionStatus.PENDING_UPLOAD)
    if status is VersionStatus.PROCESSING:
        return processing
    reason = FailureReason.UNREADABLE_MODEL if status is VersionStatus.FAILED else None
    done = transition(processing, status, now=T0, failure_reason=reason)
    repository.save_version(done, expected=VersionStatus.PROCESSING)
    return done


def test_ready_model_versions_are_listed_by_id_in_pages_without_images_or_other_states(
    engine: Engine,
) -> None:
    repository = SqlAssetRepository(engine)
    ready = sorted(_model_in(repository, VersionStatus.READY).id for _ in range(3))
    for status in (VersionStatus.PENDING_UPLOAD, VersionStatus.PROCESSING, VersionStatus.FAILED):
        _model_in(repository, status)
    _model_in(repository, VersionStatus.READY, spec=PNG)
    store = SqlMaintenanceStore(engine)

    first = store.ready_model_versions(after=None, limit=2)
    rest = store.ready_model_versions(after=first[-1], limit=2)

    assert first == ready[:2]
    assert rest == ready[2:]
    assert store.ready_model_versions(after=rest[-1], limit=2) == []


def test_dropping_the_cover_falls_back_to_the_newest_other_ready_version(engine: Engine) -> None:
    repository = SqlAssetRepository(engine)
    first = _model_in(repository, VersionStatus.READY)
    second = _model_in(repository, VersionStatus.READY, asset_id=first.asset_id)
    _model_in(repository, VersionStatus.FAILED, asset_id=first.asset_id)
    cover = _model_in(repository, VersionStatus.READY, asset_id=first.asset_id)
    _model_in(repository, VersionStatus.PROCESSING, asset_id=first.asset_id)
    for version in (first, second, cover):
        repository.promote_cover(version)
    assert repository.get(first.asset_id).cover_version_id == cover.id

    repository.drop_cover(cover)

    assert repository.get(first.asset_id).cover_version_id == second.id


def test_dropping_a_version_that_is_not_the_cover_changes_nothing(engine: Engine) -> None:
    repository = SqlAssetRepository(engine)
    first = _model_in(repository, VersionStatus.READY)
    cover = _model_in(repository, VersionStatus.READY, asset_id=first.asset_id)
    repository.promote_cover(cover)

    repository.drop_cover(first)

    assert repository.get(first.asset_id).cover_version_id == cover.id


def test_dropping_the_only_ready_version_leaves_no_cover(engine: Engine) -> None:
    repository = SqlAssetRepository(engine)
    only = _model_in(repository, VersionStatus.READY)
    repository.promote_cover(only)

    repository.drop_cover(only)

    assert repository.get(only.asset_id).cover_version_id is None
