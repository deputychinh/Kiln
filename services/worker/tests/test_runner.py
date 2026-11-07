import io
import logging
import multiprocessing
import struct
import threading
import time
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from fakes import FakeStorage, FixedClock
from glb_builder import build_glb
from PIL import Image
from sqlalchemy import Engine, text

from kiln_api.clock import DatabaseClock
from kiln_api.config import Settings
from kiln_api.container import Container, build_container
from kiln_api.domain.assets import UploadSpec, thumbnail_key
from kiln_api.domain.jobs import Job
from kiln_api.enums import Environment, FailureReason, JobStatus, VersionStatus
from kiln_api.errors import InvalidStatusTransitionError
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.jobs import SqlJobQueue
from kiln_worker.constants import WORKER_OVERRAN_EXIT_CODE
from kiln_worker.enums import RunEnd
from kiln_worker.heartbeat import LeaseTiming
from kiln_worker.recycle import RecyclePolicy
from kiln_worker.runner import Worker, build_worker
from kiln_worker.thumbnail import make_thumbnail
from kiln_worker.watchdog import JobBeacon, JobWatchdog


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


def test_a_model_gets_a_rendered_preview_and_becomes_the_cover(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, build_glb(), content_type="model/gltf-binary")

    worker.run_once()

    ready = SqlAssetRepository(engine).get_version(version.id)
    assert ready.status is VersionStatus.READY
    with Image.open(io.BytesIO(storage.blobs[thumbnail_key(ready)])) as thumb:
        assert (thumb.format, thumb.size, thumb.mode) == ("WEBP", (512, 512), "RGBA")
    assert storage.objects[thumbnail_key(ready)].content_type == "image/webp"
    assert SqlAssetRepository(engine).get(ready.asset_id).cover_version_id == ready.id


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"glTF" + b"\x00" * 16, FailureReason.UNREADABLE_MODEL),
        (
            build_glb(tweak=lambda d: d.update(extensionsRequired=["KHR_draco_mesh_compression"])),
            FailureReason.UNREADABLE_MODEL,
        ),
        (
            build_glb(tweak=lambda d: d["accessors"][1].update(count=3 * 2_000_001)),
            FailureReason.MODEL_TOO_LARGE,
        ),
    ],
)
def test_unreadable_or_oversized_models_fail_with_a_reason(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    engine: Engine,
    data: bytes,
    reason: FailureReason,
) -> None:
    version = _uploaded(container, storage, data, content_type="model/gltf-binary")

    worker.run_once()

    failed = SqlAssetRepository(engine).get_version(version.id)
    assert (failed.status, failed.failure_reason) == (VersionStatus.FAILED, reason)
    assert thumbnail_key(failed) not in storage.blobs


def test_a_model_file_over_the_size_limit_is_refused_without_downloading(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("kiln_worker.runner.MODEL_MAX_BYTES", 100)
    version = _uploaded(container, storage, build_glb(), content_type="model/gltf-binary")
    downloads: list[str] = []

    def download(key: str, *_: Any, **__: Any) -> bool:
        downloads.append(key)
        return False

    storage.download = download  # type: ignore[method-assign]

    worker.run_once()

    failed = SqlAssetRepository(engine).get_version(version.id)
    assert failed.failure_reason is FailureReason.MODEL_TOO_LARGE
    assert downloads == []


def test_a_model_replaced_between_check_and_download_is_not_rendered(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    version = _uploaded(container, storage, build_glb(), content_type="model/gltf-binary")
    real_download = storage.download

    def replaced(key: str, into: Any, *, if_match: str | None = None) -> bool:
        storage.put(key, version.size_bytes, "model/gltf-binary", build_glb())  # new ETag
        return real_download(key, into, if_match=if_match)

    storage.download = replaced  # type: ignore[method-assign]

    worker.run_once()

    failed = SqlAssetRepository(engine).get_version(version.id)
    assert failed.failure_reason is FailureReason.UPLOAD_CHANGED


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

    assert f"version {version.id}: started (attempt 1)" in caplog.text
    assert f"version {version.id}: ready" in caplog.text
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


def test_a_production_worker_uses_the_database_clock(engine: Engine, storage: FakeStorage) -> None:
    production = build_worker(engine, storage=storage)

    assert isinstance(production._clock, DatabaseClock)
    assert production._database_clock is True


@pytest.mark.parametrize(
    ("size", "reason"), [(64 * 1024 * 1024 + 1, FailureReason.IMAGE_TOO_LARGE)]
)
def test_a_webp_file_over_64_mb_is_refused_before_download(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    engine: Engine,
    size: int,
    reason: FailureReason,
) -> None:
    spec = UploadSpec(file_name="anim.webp", content_type="image/webp", size_bytes=size)
    pending = container.assets.create("Anim", spec)
    assert pending.upload is not None
    storage.put(pending.upload.fields["key"], size, "image/webp", b"RIFF")
    version = container.assets.complete_upload(pending.version.id)
    downloads: list[str] = []

    def record(key: str, _into: Any, *, if_match: str | None = None) -> bool:
        downloads.append(f"{key} {if_match}")
        return True

    storage.download = record  # type: ignore[method-assign,assignment]

    worker.run_once()

    failed = SqlAssetRepository(engine).get_version(version.id)
    assert failed.failure_reason is reason
    assert downloads == []


def test_a_job_longer_than_its_lease_is_kept_by_the_heartbeat_and_not_taken_twice(
    container: Container, storage: FakeStorage, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    timing = LeaseTiming(lease=timedelta(seconds=1), heartbeat_seconds=0.2, max_runtime_seconds=60)
    first = build_worker(engine, storage=storage, timing=timing)  # database clock
    second = build_worker(engine, storage=storage, timing=timing)
    version = _uploaded(container, storage, _png())
    rendering = threading.Event()
    real_thumbnail = make_thumbnail

    def slow_thumbnail(*args: Any) -> bytes:
        rendering.set()
        time.sleep(2.5)  # more than twice the lease
        return real_thumbnail(*args)

    monkeypatch.setattr("kiln_worker.runner.make_thumbnail", slow_thumbnail)
    worker_thread = threading.Thread(target=first.run_once)
    worker_thread.start()
    rendering.wait(5)

    taken_twice = []
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        taken_twice.append(second.run_once())
        time.sleep(0.1)
    worker_thread.join(10)

    assert not any(taken_twice)
    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.READY
    assert _job_status(engine, version.id) == ("done", 1)


def test_the_heartbeat_stops_before_the_outcome_is_written(
    container: Container,
    storage: FakeStorage,
    engine: Engine,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eager = LeaseTiming(
        lease=timedelta(minutes=5), heartbeat_seconds=0.0005, max_runtime_seconds=60
    )
    worker = build_worker(engine, storage=storage, timing=eager)
    extensions_after_finish: list[bool] = []
    finished = threading.Event()
    real_finish, real_extend = SqlJobQueue.finish, SqlJobQueue.extend

    def finish_then_linger(self: SqlJobQueue, job: Any, **kwargs: Any) -> bool:
        done = real_finish(self, job, **kwargs)
        finished.set()
        time.sleep(0.05)  # a heartbeat still running would tick here and be refused
        return done

    def watched_extend(self: SqlJobQueue, job: Any, **kwargs: Any) -> bool:
        extensions_after_finish.append(finished.is_set())
        return real_extend(self, job, **kwargs)

    monkeypatch.setattr(SqlJobQueue, "finish", finish_then_linger)
    monkeypatch.setattr(SqlJobQueue, "extend", watched_extend)
    for _ in range(5):
        _uploaded(container, storage, _png((64, 64)))

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        while worker.run_once():
            finished.clear()

    assert not any(extensions_after_finish)
    assert "lease expired or taken over" not in caplog.text
    with engine.connect() as connection:
        statuses = connection.execute(text("SELECT status FROM jobs")).scalars().all()
    assert statuses == ["done"] * 5


@pytest.mark.parametrize("outcome", ["retry", "close"])
def test_the_heartbeat_also_stops_before_a_retry_or_a_skip_is_written(
    container: Container,
    storage: FakeStorage,
    engine: Engine,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    eager = LeaseTiming(
        lease=timedelta(minutes=5), heartbeat_seconds=0.0005, max_runtime_seconds=60
    )
    worker = build_worker(engine, storage=storage, timing=eager)
    version = _uploaded(container, storage, _png((64, 64)))
    if outcome == "retry":
        storage.available = False  # the render fails: the job is requeued
    else:
        with engine.begin() as connection:  # the version moved on: the job is closed unrun
            connection.execute(
                text("UPDATE asset_versions SET status = 'ready' WHERE id = :id"),
                {"id": version.id},
            )
    written = threading.Event()
    extensions_after_write: list[bool] = []
    method = "retry" if outcome == "retry" else "finish"
    real_write, real_extend = getattr(SqlJobQueue, method), SqlJobQueue.extend

    def write_then_linger(self: SqlJobQueue, job: Any, **kwargs: Any) -> bool:
        done: bool = real_write(self, job, **kwargs)
        written.set()
        time.sleep(0.05)  # a heartbeat still running would tick here and be refused
        return done

    def watched_extend(self: SqlJobQueue, job: Any, **kwargs: Any) -> bool:
        extensions_after_write.append(written.is_set())
        return real_extend(self, job, **kwargs)

    monkeypatch.setattr(SqlJobQueue, method, write_then_linger)
    monkeypatch.setattr(SqlJobQueue, "extend", watched_extend)

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        assert worker.run_once() is True

    assert written.is_set()
    assert not any(extensions_after_write)
    assert "lease expired or taken over" not in caplog.text


def test_the_reaper_leaves_a_job_whose_owner_extended_it_after_the_reaper_looked(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _uploaded(container, storage, _png((64, 64)))
    with engine.begin() as connection:  # last attempt, lease just expired
        connection.execute(
            text(
                "UPDATE jobs SET status = 'running', attempts = 5, leased_until = :expired"
                " WHERE version_id = :id"
            ),
            {"expired": clock.now() - timedelta(seconds=1), "id": version.id},
        )
    real_exhausted = SqlJobQueue.exhausted_jobs

    def owner_extends_meanwhile(self: SqlJobQueue, **kwargs: Any) -> Any:
        found = real_exhausted(self, **kwargs)
        with engine.begin() as connection:  # the owner's heartbeat lands after the read
            connection.execute(
                text("UPDATE jobs SET leased_until = :alive WHERE version_id = :id"),
                {"alive": clock.now() + timedelta(minutes=5), "id": version.id},
            )
        return found

    monkeypatch.setattr(SqlJobQueue, "exhausted_jobs", owner_extends_meanwhile)

    worker.run_once()

    assert _job_status(engine, version.id) == ("running", 5)
    assert SqlAssetRepository(engine).get_version(version.id).status is VersionStatus.PROCESSING


def test_run_recycles_between_jobs_after_the_policy_says_so(
    container: Container,
    worker: Worker,
    storage: FakeStorage,
    engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    for _ in range(3):
        _uploaded(container, storage, _png((64, 64)))
    policy = RecyclePolicy(max_jobs=2, max_rss_bytes=10**12, rss=lambda: 300 * 1024 * 1024)

    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        end = worker.run(stop=threading.Event(), idle_seconds=0.01, recycle=policy)

    assert end is RunEnd.RECYCLE
    with engine.connect() as connection:
        statuses = sorted(connection.execute(text("SELECT status FROM jobs")).scalars())
    assert statuses == ["done", "done", "queued"]  # two jobs, never one cut short
    assert "worker recycling (max_jobs) after 2 jobs, peak memory 300 MB" in caplog.text


def test_run_without_a_policy_keeps_working_until_asked_to_stop(
    container: Container, worker: Worker, storage: FakeStorage, engine: Engine
) -> None:
    _uploaded(container, storage, _png((64, 64)))
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()

    assert worker.run(stop=stop, idle_seconds=0.01) is RunEnd.STOPPED
    with engine.connect() as connection:
        assert connection.execute(text("SELECT status FROM jobs")).scalar_one() == "done"


def test_a_hung_job_ends_the_worker_process_through_its_watchdog(
    container: Container, storage: FakeStorage, clock: FixedClock
) -> None:
    """KILN-28: a download that never returns ends the process at the job's budget."""
    version = _uploaded(container, storage, _png())
    release = threading.Event()
    ended: list[int] = []

    def hang(*_args: object, **_kwargs: object) -> bool:
        release.wait(10)  # a read that never returns, until the watchdog fires
        raise ConnectionError

    def end_process(code: int) -> None:
        ended.append(code)
        release.set()  # in production os._exit ends here; the test lets the job unwind

    storage.download = hang  # type: ignore[method-assign]
    watchdog = JobWatchdog(
        stop=threading.Event(), max_runtime_seconds=0.2, exit=end_process, poll_seconds=0.01
    )
    worker = build_worker(container.engine, storage=storage, clock=clock, watchdog=watchdog)

    started = time.monotonic()
    assert worker.run_once()

    assert ended == [WORKER_OVERRAN_EXIT_CODE]
    assert time.monotonic() - started < 5
    assert _job_status(container.engine, version.id)[1] == 1  # claimed once; retried later


def test_a_claim_is_shown_to_the_supervisor_until_its_job_is_watched(
    container: Container, storage: FakeStorage, clock: FixedClock
) -> None:
    """KILN-28: a freeze between a successful claim and the job's watch is seen too."""
    _uploaded(container, storage, _png())
    beacon = JobBeacon(multiprocessing.get_context("spawn"))
    seen: list[str] = []

    class _Watchdog(JobWatchdog):
        @contextmanager
        def watch(self, job: Job) -> Iterator[None]:
            seen.append(beacon.read().job_id)  # what the supervisor sees just before the watch
            with super().watch(job):
                yield

    watchdog = _Watchdog(stop=threading.Event(), beacon=beacon)
    worker = build_worker(container.engine, storage=storage, clock=clock, watchdog=watchdog)

    assert worker.run_once()
    assert not worker.run_once()  # nothing left: the claim marker is cleared

    assert seen == ["(claiming a job)"]
    assert beacon.read().started == 0.0


def test_a_claim_that_fails_clears_the_claim_marker(
    container: Container, storage: FakeStorage, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KILN-28: a database error during the claim must not leave the supervisor watching a job."""
    beacon = JobBeacon(multiprocessing.get_context("spawn"))
    watchdog = JobWatchdog(stop=threading.Event(), beacon=beacon)
    worker = build_worker(container.engine, storage=storage, clock=clock, watchdog=watchdog)

    def fail(*_args: object, **_kwargs: object) -> None:
        message = "database gone"
        raise RuntimeError(message)

    monkeypatch.setattr(SqlJobQueue, "claim", fail)

    with pytest.raises(RuntimeError, match="database gone"):
        worker.run_once()

    assert beacon.read().started == 0.0
