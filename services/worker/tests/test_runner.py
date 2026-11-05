import io
import logging
import struct
import threading
import time
import zlib
from datetime import timedelta
from typing import Any

import pytest
from fakes import FakeStorage, FixedClock
from PIL import Image
from sqlalchemy import Engine, text

from kiln_api.config import Settings
from kiln_api.container import Container, build_container
from kiln_api.domain.assets import UploadSpec, thumbnail_key
from kiln_api.enums import Environment, FailureReason, JobStatus, VersionStatus
from kiln_api.errors import InvalidStatusTransitionError
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.jobs import SqlJobQueue
from kiln_worker.runner import Worker, build_worker


def _png(size: tuple[int, int] = (1024, 512)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 200, 90)).save(buffer, "PNG")
    return buffer.getvalue()


def _huge_png_header() -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        return struct.pack(">I", len(body)) + kind + body + crc

    ihdr = struct.pack(">IIBBBBB", 20_000, 20_000, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00"))


@pytest.fixture
def container(
    database_url: str, engine: Engine, storage: FakeStorage, clock: FixedClock
) -> Container:
    settings = Settings(env=Environment.TEST, database_url=database_url)
    return build_container(settings, engine=engine, storage=storage, clock=clock)


@pytest.fixture
def worker(container: Container, storage: FakeStorage, clock: FixedClock) -> Worker:
    return build_worker(container.engine, storage=storage, clock=clock)


def _uploaded(
    container: Container,
    storage: FakeStorage,
    data: bytes,
    *,
    content_type: str = "image/png",
    asset_id: Any = None,
) -> Any:
    spec = UploadSpec(file_name="rock.png", content_type=content_type, size_bytes=len(data))
    service = container.assets
    pending = (
        service.create("Rock", spec) if asset_id is None else service.add_version(asset_id, spec)
    )
    assert pending.upload is not None
    storage.put(pending.upload.fields["key"], len(data), content_type, data)
    return service.complete_upload(pending.version.id)


def _job_status(engine: Engine, version_id: Any) -> tuple[str, int]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, attempts FROM jobs WHERE version_id = :id"), {"id": version_id}
        ).one()
    return row.status, row.attempts


def test_an_uploaded_image_gets_a_thumbnail_and_becomes_the_cover(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())

    assert worker.run_once() is True

    ready = SqlAssetRepository(engine).get_version(version.id)
    assert ready.status is VersionStatus.READY
    with Image.open(io.BytesIO(storage.blobs[thumbnail_key(ready)])) as thumb:
        assert (thumb.format, thumb.size) == ("WEBP", (512, 256))
    assert storage.objects[thumbnail_key(ready)].content_type == "image/webp"
    assert SqlAssetRepository(engine).get(ready.asset_id).cover_version_id == ready.id
    assert _job_status(engine, version.id) == ("done", 1)


def test_an_empty_queue_does_nothing(worker: Worker) -> None:
    assert worker.run_once() is False


def test_a_file_changed_after_completion_fails_without_rendering(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())
    storage.put(version.object_key, version.size_bytes, "image/png", _png())  # new ETag

    worker.run_once()

    failed = SqlAssetRepository(engine).get_version(version.id)
    assert failed.status is VersionStatus.FAILED
    assert failed.failure_reason is FailureReason.UPLOAD_CHANGED
    assert thumbnail_key(failed) not in storage.blobs
    assert _job_status(engine, version.id)[0] == "done"


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"this is not a png", FailureReason.UNREADABLE_IMAGE),
        (_huge_png_header(), FailureReason.IMAGE_TOO_LARGE),
    ],
)
def test_bad_images_fail_with_a_reason(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    engine: Engine,
    data: bytes,
    reason: FailureReason,
) -> None:
    version = _uploaded(container, storage, data)

    worker.run_once()

    failed = SqlAssetRepository(engine).get_version(version.id)
    assert (failed.status, failed.failure_reason) == (VersionStatus.FAILED, reason)
    assert SqlAssetRepository(engine).get(failed.asset_id).cover_version_id is None


def test_storage_outages_are_retried_with_backoff_then_given_up(
    container: Container, worker: Worker, storage: FakeStorage, clock: FixedClock, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())
    storage.available = False
    waits = []

    for _ in range(5):
        assert worker.run_once() is True
        with engine.connect() as connection:
            run_after = connection.execute(
                text("SELECT run_after FROM jobs WHERE version_id = :id"), {"id": version.id}
            ).scalar_one()
        waits.append(run_after - clock.now())
        clock.current = run_after

    gave_up = SqlAssetRepository(engine).get_version(version.id)
    assert waits[:4] == [timedelta(seconds=s) for s in (5, 25, 125, 625)]
    assert gave_up.failure_reason is FailureReason.PROCESSING_GAVE_UP
    assert _job_status(engine, version.id) == ("dead", 5)
    assert worker.run_once() is False


def test_a_job_for_a_version_that_moved_on_is_closed_without_changes(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE asset_versions SET status = 'ready' WHERE id = :id"), {"id": version.id}
        )

    worker.run_once()

    assert thumbnail_key(version) not in storage.blobs
    assert _job_status(engine, version.id)[0] == "done"


def test_a_model_is_marked_ready_without_a_thumbnail_until_kiln_5(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(
        container, storage, b"glTF" + b"\x00" * 16, content_type="model/gltf-binary"
    )

    worker.run_once()

    ready = SqlAssetRepository(engine).get_version(version.id)
    assert ready.status is VersionStatus.READY
    assert thumbnail_key(ready) not in storage.blobs


def test_an_older_version_finishing_late_does_not_take_the_cover(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    first = _uploaded(container, storage, _png())
    second = _uploaded(container, storage, _png((64, 64)), asset_id=first.asset_id)
    queue = SqlJobQueue(engine)
    with engine.begin() as connection:  # make the second job run first
        connection.execute(
            text(
                "UPDATE jobs SET run_after = run_after - interval '1 hour' WHERE version_id = :id"
            ),
            {"id": second.id},
        )

    worker.run_once()
    worker.run_once()

    assert SqlAssetRepository(engine).get(first.asset_id).cover_version_id == second.id
    assert queue.counts() == {JobStatus.DONE: 2}


def test_job_logs_name_the_job_but_not_the_file(
    container: Container, worker: Worker, storage: FakeStorage, caplog: pytest.LogCaptureFixture
) -> None:
    version = _uploaded(container, storage, _png())

    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        worker.run_once()

    assert str(version.id) in caplog.text
    assert "ready" in caplog.text
    assert "rock.png" not in caplog.text


def test_the_loop_sleeps_when_idle_and_stops_when_asked(worker: Worker) -> None:
    stop = threading.Event()
    loop = threading.Thread(target=worker.run, kwargs={"stop": stop, "idle_seconds": 0.05})
    loop.start()
    stop.set()
    loop.join(timeout=2)

    assert not loop.is_alive()


def test_a_version_changed_while_rendering_closes_the_job_without_overwriting(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())

    def someone_else_finishes() -> None:
        storage.on_head = None
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE asset_versions SET status = 'failed', failure_reason = 'UPLOAD_CHANGED'"
                    " WHERE id = :id"
                ),
                {"id": version.id},
            )

    storage.on_head = someone_else_finishes
    worker.run_once()

    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.FAILED
    assert _job_status(engine, version.id)[0] == "done"


def test_an_unexpected_error_is_retried_and_never_kills_the_worker(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())

    def boom() -> None:
        message = "bug in a decoder"
        raise RuntimeError(message)

    storage.on_head = boom
    assert worker.run_once() is True

    with engine.connect() as connection:
        status, attempts, error = connection.execute(
            text("SELECT status, attempts, last_error FROM jobs WHERE version_id = :id"),
            {"id": version.id},
        ).one()
    assert (status, attempts, error) == ("queued", 1, "RuntimeError")
    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.PROCESSING


def test_a_job_that_crashed_the_worker_five_times_is_buried_and_its_version_failed(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
) -> None:
    version = _uploaded(container, storage, _png())
    queue = SqlJobQueue(engine)
    for _ in range(5):  # each claim "crashes": nobody finishes, the lease expires
        assert queue.claim(lease=timedelta(minutes=5), max_attempts=5, now=clock.now())
        clock.advance(timedelta(minutes=5, seconds=1).total_seconds())

    assert worker.run_once() is False

    failed = SqlAssetRepository(engine).get_version(version.id)
    assert failed.failure_reason is FailureReason.PROCESSING_GAVE_UP
    assert _job_status(engine, version.id) == ("dead", 5)


def test_a_worker_that_lost_its_lease_does_not_overwrite_the_new_owner(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
) -> None:
    version = _uploaded(container, storage, _png())

    def slow_render_and_someone_else_reclaims() -> None:
        storage.on_head = None
        clock.advance(timedelta(minutes=5, seconds=1).total_seconds())
        SqlJobQueue(engine).claim(lease=timedelta(minutes=5), max_attempts=5, now=clock.now())

    storage.on_head = slow_render_and_someone_else_reclaims
    worker.run_once()

    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.PROCESSING
    assert _job_status(engine, version.id) == ("running", 2)


def test_a_failure_between_saving_the_version_and_the_cover_rolls_both_back(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _uploaded(container, storage, _png())

    def broken(*_: object, **__: object) -> None:
        message = "connection dropped"
        raise RuntimeError(message)

    monkeypatch.setattr(SqlAssetRepository, "promote_cover", broken)
    worker.run_once()

    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.PROCESSING
    assert _job_status(engine, version.id) == ("queued", 1)


def test_an_object_replaced_between_head_and_download_is_reported_as_changed(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())
    original_download = storage.download

    def swapped(key: str, into: Any, *, if_match: str | None = None) -> bool:
        storage.put(key, version.size_bytes, "image/png", _png())  # new ETag after HEAD
        return original_download(key, into, if_match=if_match)

    storage.download = swapped  # type: ignore[method-assign]
    worker.run_once()

    failed = SqlAssetRepository(engine).get_version(version.id)
    assert failed.failure_reason is FailureReason.UPLOAD_CHANGED


def test_the_loop_survives_a_database_outage(storage: FakeStorage) -> None:
    from sqlalchemy import create_engine  # noqa: PLC0415 - local to this scenario

    down = create_engine("postgresql+psycopg://kiln:kiln@127.0.0.1:9/kiln_test")
    worker = build_worker(down, storage=storage)
    stop = threading.Event()
    loop = threading.Thread(target=worker.run, kwargs={"stop": stop, "idle_seconds": 0.02})
    loop.start()
    time.sleep(0.2)

    assert loop.is_alive()
    stop.set()
    loop.join(timeout=2)
    assert not loop.is_alive()


class _RecordingEvent(threading.Event):
    def __init__(self) -> None:
        super().__init__()
        self.waits: list[float | None] = []

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout)
        self.set()
        return True


def test_an_idle_worker_waits_for_the_poll_interval(worker: Worker) -> None:
    stop = _RecordingEvent()

    worker.run(stop=stop, idle_seconds=0.75)

    assert stop.waits == [0.75]


def test_a_legacy_version_without_a_recorded_etag_is_processed_as_it_is(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE asset_versions SET etag = NULL WHERE id = :id"), {"id": version.id}
        )

    worker.run_once()

    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.READY


def _expire_and_reclaim(engine: Engine, clock: FixedClock) -> None:
    clock.advance(timedelta(minutes=5, seconds=1).total_seconds())
    SqlJobQueue(engine).claim(lease=timedelta(minutes=5), max_attempts=5, now=clock.now())


def test_a_retry_by_a_worker_that_lost_its_lease_changes_nothing(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
) -> None:
    version = _uploaded(container, storage, _png())

    def reclaimed_then_failing() -> None:
        storage.on_head = None
        _expire_and_reclaim(engine, clock)
        message = "transient"
        raise RuntimeError(message)

    storage.on_head = reclaimed_then_failing
    worker.run_once()

    assert _job_status(engine, version.id) == ("running", 2)


def test_closing_a_skipped_job_after_losing_the_lease_changes_nothing(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _uploaded(container, storage, _png())
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE asset_versions SET status = 'ready' WHERE id = :id"), {"id": version.id}
        )
    original = SqlAssetRepository.get_version

    def reclaim_first(repo: SqlAssetRepository, version_id: Any) -> Any:
        _expire_and_reclaim(engine, clock)
        return original(repo, version_id)

    monkeypatch.setattr(SqlAssetRepository, "get_version", reclaim_first)
    worker.run_once()

    assert _job_status(engine, version.id) == ("running", 2)


def _exhaust_attempts(engine: Engine, version_id: Any) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE jobs SET attempts = 4 WHERE version_id = :id"), {"id": version_id}
        )


def _fail_render(storage: FakeStorage) -> None:
    def boom() -> None:
        message = "still broken"
        raise RuntimeError(message)

    storage.on_head = boom


def test_giving_up_after_losing_the_lease_leaves_the_version_alone(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    engine: Engine,
) -> None:
    version = _uploaded(container, storage, _png())
    _exhaust_attempts(engine, version.id)

    def reclaimed_then_failing() -> None:
        storage.on_head = None
        with engine.begin() as connection:  # another worker re-claims the 5th attempt
            connection.execute(
                text("UPDATE jobs SET attempts = 6 WHERE version_id = :id"), {"id": version.id}
            )
        message = "boom"
        raise RuntimeError(message)

    storage.on_head = reclaimed_then_failing
    worker.run_once()

    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.PROCESSING
    assert _job_status(engine, version.id) == ("running", 6)


def test_giving_up_on_a_version_that_moved_on_only_buries_the_job(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, _png())
    _exhaust_attempts(engine, version.id)

    def moved_on_then_failing() -> None:
        storage.on_head = None
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE asset_versions SET status = 'ready' WHERE id = :id"),
                {"id": version.id},
            )
        message = "boom"
        raise RuntimeError(message)

    storage.on_head = moved_on_then_failing
    worker.run_once()

    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.READY
    assert _job_status(engine, version.id)[0] == "dead"


def test_giving_up_when_the_version_changes_at_the_last_moment_does_not_crash(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _uploaded(container, storage, _png())
    _exhaust_attempts(engine, version.id)
    _fail_render(storage)

    def changed_meanwhile(*_: object, **__: object) -> None:
        raise InvalidStatusTransitionError(VersionStatus.READY, VersionStatus.FAILED)

    monkeypatch.setattr(SqlAssetRepository, "save_version", changed_meanwhile)
    worker.run_once()

    assert _job_status(engine, version.id)[0] == "dead"
