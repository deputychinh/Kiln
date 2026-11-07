"""KILN-36: re-check ready models under the current rules (real Postgres, fake storage)."""

import io
import logging
from collections.abc import Callable
from typing import IO
from uuid import UUID

import pytest
from db_fixtures import artist
from fakes import FakeStorage, FixedClock
from glb_builder import build_glb, cycle_in_a_second_scene, dag_in_a_second_scene
from PIL import Image
from sqlalchemy import Engine

from kiln_api.config import Settings
from kiln_api.container import Container, build_container
from kiln_api.domain.assets import AssetVersion, UploadSpec
from kiln_api.enums import Environment, FailureReason, VersionStatus
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_worker import recheck as recheck_module
from kiln_worker.errors import ModelTooLargeError, PreviewCrashedError
from kiln_worker.recheck import ModelRecheck, RecheckReport, build_recheck, main
from kiln_worker.runner import build_worker
from kiln_worker.sandbox import render_glb_sandboxed

GLB = "model/gltf-binary"
DAG = build_glb(tweak=dag_in_a_second_scene)
CYCLE = build_glb(tweak=cycle_in_a_second_scene)


@pytest.fixture
def container(
    database_url: str, engine: Engine, storage: FakeStorage, clock: FixedClock
) -> Container:
    settings = Settings(env=Environment.TEST, database_url=database_url)
    return build_container(settings, engine=engine, storage=storage, clock=clock)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 200, 90)).save(buffer, "PNG")
    return buffer.getvalue()


def _old_rules(source: IO[bytes]) -> bytes:
    """What the worker did before KILN-36 for these files: a preview, so the version is ready."""
    source.read()
    return b"preview"


def _ready(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
    *,
    content_type: str = GLB,
    asset_id: UUID | None = None,
) -> AssetVersion:
    """Publish `data` and process it the way the worker did before KILN-36 (it became ready)."""
    spec = UploadSpec(file_name="crate.glb", content_type=content_type, size_bytes=len(data))
    service = container.assets
    by = artist(container.engine)
    pending = (
        service.create(by, "Crate", spec)
        if asset_id is None
        else service.add_version(by, asset_id, spec)
    )
    assert pending.upload is not None
    storage.put(pending.upload.fields["key"], len(data), content_type, data)
    service.complete_upload(by, pending.version.id)
    with monkeypatch.context() as patch:
        patch.setattr("kiln_worker.runner.render_glb_sandboxed", _old_rules)
        assert build_worker(container.engine, storage=storage, clock=clock).run_once()
    clock.advance(1)
    version = SqlAssetRepository(container.engine).get_version(pending.version.id)
    assert version.status is VersionStatus.READY
    return version


def _state(engine: Engine, version: AssetVersion) -> tuple[VersionStatus, FailureReason | None]:
    stored = SqlAssetRepository(engine).get_version(version.id)
    return stored.status, stored.failure_reason


def _cover(engine: Engine, version: AssetVersion) -> UUID | None:
    return SqlAssetRepository(engine).get(version.asset_id).cover_version_id


def _recheck(
    engine: Engine,
    storage: FakeStorage,
    clock: FixedClock,
    *,
    render: Callable[[IO[bytes]], bytes] = render_glb_sandboxed,
    batch_size: int = 100,
) -> ModelRecheck:
    return build_recheck(engine, storage=storage, clock=clock, render=render, batch_size=batch_size)


@pytest.mark.parametrize("data", [DAG, CYCLE], ids=["dag-in-second-scene", "cycle-in-second-scene"])
def test_a_ready_model_the_current_rules_refuse_fails_and_the_cover_falls_back(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
) -> None:
    good = _ready(container, storage, clock, monkeypatch, build_glb())
    bad = _ready(container, storage, clock, monkeypatch, data, asset_id=good.asset_id)
    assert _cover(engine, bad) == bad.id

    report = _recheck(engine, storage, clock).run()

    assert report == RecheckReport(checked=2, kept=1, unreadable=1)
    assert _state(engine, bad) == (VersionStatus.FAILED, FailureReason.UNREADABLE_MODEL)
    assert _state(engine, good) == (VersionStatus.READY, None)
    assert _cover(engine, bad) == good.id


def test_a_ready_model_over_the_current_size_limit_fails_as_too_large_and_leaves_no_cover(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _ready(container, storage, clock, monkeypatch, build_glb())
    monkeypatch.setattr(recheck_module, "MODEL_MAX_BYTES", version.size_bytes - 1)

    report = _recheck(engine, storage, clock).run()

    assert report == RecheckReport(checked=1, too_large=1)
    assert _state(engine, version) == (VersionStatus.FAILED, FailureReason.MODEL_TOO_LARGE)
    assert _cover(engine, version) is None


def test_a_model_too_complex_for_the_sandbox_fails_as_too_large(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _ready(container, storage, clock, monkeypatch, build_glb())

    def too_large(_: IO[bytes]) -> bytes:
        raise ModelTooLargeError  # what the sandbox raises past its time or memory limits

    report = _recheck(engine, storage, clock, render=too_large).run()

    assert report == RecheckReport(checked=1, too_large=1)
    assert _state(engine, version) == (VersionStatus.FAILED, FailureReason.MODEL_TOO_LARGE)


def test_a_failing_version_that_is_not_the_cover_leaves_the_cover_alone(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _ready(container, storage, clock, monkeypatch, DAG)
    good = _ready(container, storage, clock, monkeypatch, build_glb(), asset_id=bad.asset_id)

    _recheck(engine, storage, clock).run()

    assert _state(engine, bad) == (VersionStatus.FAILED, FailureReason.UNREADABLE_MODEL)
    assert _cover(engine, good) == good.id


def test_images_and_versions_that_are_not_ready_are_never_checked(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _ready(container, storage, clock, monkeypatch, _png(), content_type="image/png")
    spec = UploadSpec(file_name="crate.glb", content_type=GLB, size_bytes=len(DAG))
    pending = container.assets.create(artist(container.engine), "Waiting", spec).version
    checked: list[bytes] = []

    def render(source: IO[bytes]) -> bytes:
        checked.append(source.read())
        return b""

    report = _recheck(engine, storage, clock, render=render).run()

    assert report == RecheckReport()
    assert checked == []
    assert _state(engine, image) == (VersionStatus.READY, None)
    assert _state(engine, pending) == (VersionStatus.PENDING_UPLOAD, None)


def test_running_it_twice_changes_nothing_the_second_time(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = _ready(container, storage, clock, monkeypatch, build_glb())
    bad = _ready(container, storage, clock, monkeypatch, DAG, asset_id=good.asset_id)
    _recheck(engine, storage, clock).run()
    before = SqlAssetRepository(engine).get_version(bad.id)

    report = _recheck(engine, storage, clock).run()

    assert report == RecheckReport(checked=1, kept=1)
    assert SqlAssetRepository(engine).get_version(bad.id) == before
    assert _cover(engine, good) == good.id


def test_a_version_another_run_failed_first_is_skipped_and_written_once(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = _ready(container, storage, clock, monkeypatch, build_glb())
    bad = _ready(container, storage, clock, monkeypatch, DAG, asset_id=good.asset_id)
    other: list[RecheckReport] = []

    def render_after_the_other_run(source: IO[bytes]) -> bytes:
        if not other:  # while this run checks the file, a second run does all of it
            other.append(_recheck(engine, storage, clock).run())
        return render_glb_sandboxed(source)

    report = _recheck(engine, storage, clock, render=render_after_the_other_run).run()

    assert other == [RecheckReport(checked=2, kept=1, unreadable=1)]
    assert report == RecheckReport(checked=2, kept=1, skipped=1)  # read ready, written by other
    assert _state(engine, bad) == (VersionStatus.FAILED, FailureReason.UNREADABLE_MODEL)
    assert _cover(engine, good) == good.id


def test_a_newer_version_a_worker_makes_ready_meanwhile_still_becomes_the_cover(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = _ready(container, storage, clock, monkeypatch, build_glb())
    bad = _ready(container, storage, clock, monkeypatch, DAG, asset_id=good.asset_id)
    newer: list[AssetVersion] = []

    def render_while_a_worker_publishes(source: IO[bytes]) -> bytes:
        if not newer:
            newer.append(
                _ready(container, storage, clock, monkeypatch, build_glb(), asset_id=good.asset_id)
            )
        return render_glb_sandboxed(source)

    _recheck(engine, storage, clock, render=render_while_a_worker_publishes).run()

    assert _state(engine, bad) == (VersionStatus.FAILED, FailureReason.UNREADABLE_MODEL)
    assert _cover(engine, good) == newer[0].id


@pytest.mark.parametrize("change", ["replaced", "missing"])
def test_a_ready_model_whose_stored_file_changed_or_vanished_is_skipped_not_failed(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    version = _ready(container, storage, clock, monkeypatch, DAG)
    if change == "replaced":
        storage.put(version.object_key, len(DAG), GLB, DAG)  # a new ETag
    else:
        storage.delete(version.object_key)

    report = _recheck(engine, storage, clock).run()

    assert report == RecheckReport(checked=1, skipped=1)
    assert _state(engine, version) == (VersionStatus.READY, None)


def test_a_preview_process_that_crashes_skips_the_version(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _ready(container, storage, clock, monkeypatch, DAG)

    def crash(_: IO[bytes]) -> bytes:
        raise PreviewCrashedError

    report = _recheck(engine, storage, clock, render=crash).run()

    assert report == RecheckReport(checked=1, skipped=1)
    assert _state(engine, version) == (VersionStatus.READY, None)


def test_storage_going_down_stops_the_run_and_says_so(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _ready(container, storage, clock, monkeypatch, DAG)
    _ready(container, storage, clock, monkeypatch, DAG)
    storage.available = False

    report = _recheck(engine, storage, clock).run()

    assert report == RecheckReport(checked=1, skipped=1, storage_down=True)
    assert _state(engine, version) == (VersionStatus.READY, None)


def test_every_ready_model_is_checked_in_batches(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = [_ready(container, storage, clock, monkeypatch, DAG) for _ in range(3)]

    report = _recheck(engine, storage, clock, batch_size=2).run()

    assert report == RecheckReport(checked=3, unreadable=3)
    assert {_state(engine, v) for v in versions} == {
        (VersionStatus.FAILED, FailureReason.UNREADABLE_MODEL)
    }


def test_the_command_logs_counts_only_and_exits_zero(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    version = _ready(container, storage, clock, monkeypatch, DAG)
    monkeypatch.setattr(recheck_module, "build_storage", lambda _: storage)

    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        code = main(Settings(env=Environment.TEST, database_url=database_url))

    assert code == 0
    assert "re-check: 1 ready models checked, 0 kept, 1 unreadable, 0 too large" in caplog.text
    assert str(version.id) not in caplog.text
    assert str(version.asset_id) not in caplog.text
    assert "Crate" not in caplog.text


def test_the_command_exits_non_zero_when_storage_is_down(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready(container, storage, clock, monkeypatch, DAG)
    storage.available = False
    monkeypatch.setattr(recheck_module, "build_storage", lambda _: storage)

    assert main(Settings(env=Environment.TEST, database_url=database_url)) == 1


def test_build_recheck_reads_the_database_clock_by_default(
    engine: Engine, storage: FakeStorage
) -> None:
    assert build_recheck(engine, storage=storage).run() == RecheckReport()


def test_a_file_replaced_between_its_check_and_its_download_is_skipped(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = _ready(container, storage, clock, monkeypatch, DAG)
    monkeypatch.setattr(storage, "download", lambda *_, **__: False)  # If-Match failed

    report = _recheck(engine, storage, clock).run()

    assert report == RecheckReport(checked=1, skipped=1)
    assert _state(engine, version) == (VersionStatus.READY, None)


def test_a_version_that_left_ready_between_the_two_reads_is_not_checked(
    container: Container,
    storage: FakeStorage,
    clock: FixedClock,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready(container, storage, clock, monkeypatch, DAG)
    monkeypatch.setattr(SqlAssetRepository, "versions_by_id", lambda *_: {})  # gone meanwhile

    assert _recheck(engine, storage, clock).run() == RecheckReport()
