import logging
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fakes import FakeStorage, FixedClock
from pydantic import ValidationError
from sqlalchemy import Engine, text

from kiln_api.config import Settings
from kiln_api.container import Container, build_container
from kiln_api.domain.assets import UploadSpec, upload_key
from kiln_api.enums import Environment, FailureReason, VersionStatus
from kiln_api.errors import DatabaseUnavailableError
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.jobs import SqlJobQueue
from kiln_api.repositories.maintenance import SqlMaintenanceStore
from kiln_api.repositories.unit_of_work import SqlUnitOfWork
from kiln_worker import maintenance as maintenance_module
from kiln_worker.config import WorkerSettings
from kiln_worker.runner import Worker, WorkerPorts, build_worker

DAY = timedelta(hours=24)
SPEC = UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=10)


@pytest.fixture
def container(
    database_url: str, engine: Engine, storage: FakeStorage, clock: FixedClock
) -> Container:
    settings = Settings(env=Environment.TEST, database_url=database_url)
    return build_container(settings, engine=engine, storage=storage, clock=clock)


@pytest.fixture
def worker(container: Container, storage: FakeStorage, clock: FixedClock) -> Worker:
    return build_worker(
        container.engine, storage=storage, clock=clock, maintenance_interval=timedelta(hours=1)
    )


def _pending(container: Container, storage: FakeStorage, *, uploaded: bool = True) -> Any:
    """A version whose file was uploaded (or not) but never completed."""
    pending = container.assets.create("Rock", SPEC)
    assert pending.upload is not None
    if uploaded:
        storage.put(
            pending.upload.fields["key"], 10, "image/png", modified_at=pending.version.created_at
        )
    return pending.version


def _status(engine: Engine, version_id: Any) -> tuple[VersionStatus, FailureReason | None]:
    version = SqlAssetRepository(engine).get_version(version_id)
    return version.status, version.failure_reason


def _run(worker: Worker) -> Any:
    return worker.maintain_if_due(now=0.0)


def test_an_upload_never_completed_within_24_hours_expires_and_its_staging_object_goes(
    container: Container, worker: Worker, storage: FakeStorage, clock: FixedClock, engine: Engine
) -> None:
    abandoned = _pending(container, storage)
    clock.advance(60)
    young = _pending(container, storage)
    clock.advance(DAY.total_seconds() - 30)  # abandoned is 24 h 30 s old, young 23 h 59 m 30 s

    report = _run(worker)

    assert report.expired_versions == 1
    assert _status(engine, abandoned.id) == (VersionStatus.FAILED, FailureReason.UPLOAD_EXPIRED)
    assert upload_key(abandoned) not in storage.objects
    assert _status(engine, young.id) == (VersionStatus.PENDING_UPLOAD, None)
    assert upload_key(young) in storage.objects


def test_a_completion_after_expiry_returns_the_expired_version_unchanged(
    container: Container, worker: Worker, storage: FakeStorage, clock: FixedClock
) -> None:
    abandoned = _pending(container, storage)
    clock.advance(DAY.total_seconds() + 1)
    _run(worker)

    completed = container.assets.complete_upload(abandoned.id)

    assert (completed.status, completed.failure_reason) == (
        VersionStatus.FAILED,
        FailureReason.UPLOAD_EXPIRED,
    )


def test_a_version_completed_while_maintenance_runs_is_left_alone(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _pending(container, storage)
    clock.advance(DAY.total_seconds() + 1)
    original = SqlAssetRepository.versions_by_id
    raced: list[bool] = []

    def complete_first(self: SqlAssetRepository, version_ids: Any) -> Any:
        found = original(self, version_ids)  # read while still pending...
        if not raced:
            raced.append(True)
            container.assets.complete_upload(version.id)  # ...then the client wins the race
        return found

    monkeypatch.setattr(SqlAssetRepository, "versions_by_id", complete_first)

    report = _run(worker)

    assert report.expired_versions == 0
    assert _status(engine, version.id) == (VersionStatus.PROCESSING, None)


def test_old_staging_objects_go_only_when_their_version_moved_on_or_is_gone(
    container: Container, worker: Worker, storage: FakeStorage, clock: FixedClock
) -> None:
    long_ago = clock.now() - DAY - timedelta(seconds=1)
    completed = container.assets.create("Done", SPEC)
    assert completed.upload is not None
    storage.put(completed.upload.fields["key"], 10, "image/png")
    container.assets.complete_upload(completed.version.id)
    leftover = upload_key(completed.version)  # a deletion after promotion that failed
    storage.put(leftover, 10, "image/png", modified_at=long_ago)
    orphan = f"uploads/{uuid4()}/{uuid4()}"  # its version no longer exists
    storage.put(orphan, 10, "image/png", modified_at=long_ago)
    waiting = _pending(container, storage)  # young pending version: never touched...
    # ...even when storage's clock makes its object look old (clock skew).
    storage.put(upload_key(waiting), 10, "image/png", modified_at=long_ago)
    stranger = "uploads/not-a-kiln-key"
    storage.put(stranger, 10, "image/png", modified_at=long_ago)
    outside = f"assets/{uuid4()}/v1/x.png"
    storage.put(outside, 10, "image/png", modified_at=long_ago)
    young_orphan = f"uploads/{uuid4()}/{uuid4()}"
    storage.put(young_orphan, 10, "image/png", modified_at=clock.now())

    report = _run(worker)

    assert report.deleted_objects == 2
    assert leftover not in storage.objects
    assert orphan not in storage.objects
    for kept in (upload_key(waiting), stranger, outside, young_orphan):
        assert kept in storage.objects


def test_expired_idempotency_keys_are_purged(
    container: Container, worker: Worker, clock: FixedClock, engine: Engine
) -> None:
    container.assets.create("Keyed", SPEC, idempotency_key="k-1")
    clock.advance(DAY.total_seconds() + 1)

    report = _run(worker)

    assert report.purged_keys == 1
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM idempotency_keys")).scalar() == 0


def test_maintenance_runs_once_per_interval_and_asks_at_most_once_a_minute(
    worker: Worker, clock: FixedClock
) -> None:
    assert worker.maintain_if_due(now=0.0) is not None
    clock.advance(2 * 60 * 60)
    assert worker.maintain_if_due(now=30.0) is None  # local gate: asked 30 s ago
    assert worker.maintain_if_due(now=60.0) is not None  # due again after the 1 h interval
    assert worker.maintain_if_due(now=120.0) is None  # the lease: another run within 1 h


def test_each_sweep_handles_one_batch_per_run(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maintenance_module, "MAINTENANCE_BATCH_SIZE", 2)
    versions = [_pending(container, storage, uploaded=False) for _ in range(3)]
    clock.advance(DAY.total_seconds() + 1)

    first = _run(worker)
    clock.advance(60 * 60)
    second = worker.maintain_if_due(now=60.0)

    assert first is not None
    assert second is not None
    assert (first.expired_versions, second.expired_versions) == (2, 1)
    assert all(_status(engine, v.id)[0] is VersionStatus.FAILED for v in versions)


def test_a_storage_outage_stops_the_storage_work_jobs_go_on_and_a_later_run_finishes(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    abandoned = _pending(container, storage)
    container.assets.create("Keyed", SPEC, idempotency_key="k-1")
    clock.advance(DAY.total_seconds() + 1)
    storage.delete_available = False

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        report = _run(worker)

    assert report is not None
    assert report.storage_down is True
    assert report.purged_keys == 1  # the database work still happens
    assert "storage unavailable (StorageUnavailableError)" in caplog.text
    # Saved before deleting: the version is expired, the object is still there.
    assert _status(engine, abandoned.id) == (VersionStatus.FAILED, FailureReason.UPLOAD_EXPIRED)
    assert upload_key(abandoned) in storage.objects
    assert worker.run_once() is False  # job processing is unaffected

    storage.delete_available = True
    clock.advance(60 * 60)
    later = worker.maintain_if_due(now=60.0)
    assert later is not None
    assert later.deleted_objects == 1
    assert upload_key(abandoned) not in storage.objects


def test_a_listing_failure_keeps_what_was_already_expired(
    container: Container, worker: Worker, storage: FakeStorage, clock: FixedClock, engine: Engine
) -> None:
    abandoned = _pending(container, storage)
    clock.advance(DAY.total_seconds() + 1)
    storage.list_available = False

    report = _run(worker)

    assert report is not None
    assert (report.expired_versions, report.storage_down) == (1, True)
    assert _status(engine, abandoned.id)[0] is VersionStatus.FAILED


def test_a_database_failure_is_logged_and_jobs_go_on(
    worker: Worker, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*_: object, **__: object) -> bool:
        raise DatabaseUnavailableError

    monkeypatch.setattr(SqlMaintenanceStore, "try_start", broken)

    with caplog.at_level(logging.ERROR, logger="kiln_worker"):
        assert _run(worker) is None

    assert "maintenance failed: DatabaseUnavailableError" in caplog.text
    assert worker.run_once() is False


def test_expiry_after_a_racing_promotion_also_removes_the_final_object(
    container: Container, worker: Worker, storage: FakeStorage, clock: FixedClock
) -> None:
    version = _pending(container, storage)
    clock.advance(DAY.total_seconds() + 1)
    # A completion copied staging to the final key and deleted staging, then lost the race.
    staged = storage.objects[upload_key(version)]
    storage.promote(source_key=upload_key(version), target_key=version.object_key, etag=staged.etag)
    storage.delete(upload_key(version))

    report = _run(worker)

    assert report is not None
    assert report.expired_versions == 1
    assert version.object_key not in storage.objects
    assert container.assets.complete_upload(version.id).status is VersionStatus.FAILED


def test_a_version_gone_before_expiry_is_skipped(
    worker: Worker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SqlMaintenanceStore, "stale_pending_versions", lambda *_, **__: [uuid4()])

    report = _run(worker)

    assert report is not None
    assert report.expired_versions == 0


def test_keys_that_must_stay_do_not_use_up_the_batch(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maintenance_module, "MAINTENANCE_BATCH_SIZE", 2)
    long_ago = clock.now() - DAY - timedelta(seconds=1)
    for junk in ("uploads/0-junk-a", "uploads/0-junk-b", "uploads/0-junk-c"):
        storage.put(junk, 10, "image/png", modified_at=long_ago)  # sorts first, never deletable
    for _ in range(3):  # young waiting versions whose objects look old (clock skew)
        waiting = _pending(container, storage)
        storage.put(upload_key(waiting), 10, "image/png", modified_at=long_ago)
    orphan = f"uploads/{'f' * 8}-ffff-7fff-bfff-{'f' * 12}/{uuid4()}"  # sorts last
    storage.put(orphan, 10, "image/png", modified_at=long_ago)

    report = _run(worker)

    assert report is not None
    assert report.deleted_objects == 1
    assert orphan not in storage.objects


def test_the_staging_scan_is_bounded_and_looks_versions_up_in_chunks(
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maintenance_module, "MAINTENANCE_SCAN_LIMIT", 5)
    monkeypatch.setattr(maintenance_module, "MAINTENANCE_LOOKUP_CHUNK", 2)
    long_ago = clock.now() - DAY - timedelta(seconds=1)
    orphans = sorted(f"uploads/{uuid4()}/{uuid4()}" for _ in range(6))
    for key in orphans:
        storage.put(key, 10, "image/png", modified_at=long_ago)
    lookups: list[int] = []
    original = SqlAssetRepository.versions_by_id

    def counted(self: SqlAssetRepository, ids: Any) -> Any:
        lookups.append(len(ids))
        return original(self, ids)

    monkeypatch.setattr(SqlAssetRepository, "versions_by_id", counted)

    report = _run(worker)

    assert report is not None
    assert report.deleted_objects == 5  # the sixth waits for the next run
    assert storage.listed == 5
    assert orphans[-1] in storage.objects
    assert lookups == [2, 2, 1]


def test_the_staging_sweep_stops_after_one_batch_of_deletions(
    worker: Worker, storage: FakeStorage, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(maintenance_module, "MAINTENANCE_BATCH_SIZE", 2)
    long_ago = clock.now() - DAY - timedelta(seconds=1)
    orphans = sorted(f"uploads/{uuid4()}/{uuid4()}" for _ in range(3))
    for key in orphans:
        storage.put(key, 10, "image/png", modified_at=long_ago)

    report = _run(worker)

    assert report is not None
    assert report.deleted_objects == 2
    assert [key in storage.objects for key in orphans] == [False, False, True]


def test_the_maintenance_interval_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        WorkerSettings(maintenance_interval_seconds=0)


def test_one_log_line_per_run_with_counts_and_no_names(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _pending(container, storage)
    clock.advance(DAY.total_seconds() + 1)

    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        _run(worker)

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("maintenance:")]
    assert len(lines) == 1
    assert lines[0].startswith(
        "maintenance: 1 abandoned versions expired, 0 staging objects deleted,"
        " 0 idempotency keys purged in"
    )
    assert "Rock" not in caplog.text
    assert "rock.png" not in caplog.text


def test_a_worker_without_maintenance_never_maintains(
    container: Container, storage: FakeStorage, clock: FixedClock
) -> None:
    ports = WorkerPorts(
        jobs=SqlJobQueue(container.engine),
        assets=SqlAssetRepository(container.engine),
        storage=storage,
        unit_of_work=SqlUnitOfWork(container.engine),
    )
    plain = Worker(ports, clock, database_clock=False)

    assert plain.maintain_if_due(now=0.0) is None
