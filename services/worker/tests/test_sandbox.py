import contextlib
import io
import logging
import multiprocessing
import os
import resource
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import sandbox_bodies
from glb_builder import assemble, build_glb
from PIL import Image

from kiln_worker.constants import MODEL_SANDBOX_CPU_SECONDS, MODEL_SANDBOX_MEMORY_BYTES
from kiln_worker.errors import ModelTooLargeError, PreviewCrashedError, UnreadableModelError
from kiln_worker.sandbox import (
    _child_main,
    _watch_parent,
    limit_child,
    remove_stale_folders,
    render_file,
    render_glb_sandboxed,
    run_child,
)


def _overdraw(triangles: int) -> bytes:
    """`triangles` copies of a full-frame triangle: cheap to store, slow to draw."""
    corners = np.tile(
        np.array([[-1, -1, 0], [1, -1, 0], [0, 1, 0.001]], dtype="<f4"), (triangles, 1)
    )
    corners[:, 2] += np.repeat(np.arange(triangles, dtype="<f4") * 1e-6, 3)
    data = corners.tobytes()
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(data)}],
        "bufferViews": [{"buffer": 0, "byteLength": len(data)}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(corners), "type": "VEC3"}
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }
    return assemble(document, data)


def _sandboxed(data: bytes, **kwargs: float) -> bytes:
    return render_glb_sandboxed(io.BytesIO(data), **kwargs)


def test_a_model_renders_in_the_child_process() -> None:
    preview = _sandboxed(build_glb())

    with Image.open(io.BytesIO(preview)) as image:
        assert (image.format, image.size) == ("WEBP", (512, 512))


def test_an_unreadable_model_is_reported_from_the_child() -> None:
    with pytest.raises(UnreadableModelError):
        _sandboxed(b"glTF" + b"\x00" * 16)


def test_a_model_over_its_geometry_budget_is_reported_from_the_child() -> None:
    with pytest.raises(ModelTooLargeError):
        _sandboxed(build_glb(tweak=lambda d: d["accessors"][1].update(count=3 * 2_000_001)))


def test_a_real_render_over_its_time_limit_is_refused() -> None:
    started = time.monotonic()

    with pytest.raises(ModelTooLargeError, match="preview took more than"):
        _sandboxed(_overdraw(1_000_000), seconds=1.0)

    assert time.monotonic() - started < 5  # killed: drawing alone would run for 20 s


def test_a_child_over_its_time_limit_is_killed_and_gone(tmp_path: Path) -> None:
    target = tmp_path / "out.webp"

    with pytest.raises(ModelTooLargeError, match="preview took more than"):
        run_child(tmp_path / "model.glb", target, seconds=1.0, body=sandbox_bodies.sleep_forever)

    pid = int(target.with_suffix(".pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)  # the child no longer exists


def test_a_child_killed_like_the_oom_killer_does_means_too_large(tmp_path: Path) -> None:
    with pytest.raises(ModelTooLargeError):
        run_child(
            tmp_path / "m.glb", tmp_path / "o.webp", seconds=30, body=sandbox_bodies.kill_self
        )


def test_a_child_stopped_by_its_cpu_limit_means_too_large(tmp_path: Path) -> None:
    with pytest.raises(ModelTooLargeError):
        run_child(
            tmp_path / "m.glb", tmp_path / "o.webp", seconds=30, body=sandbox_bodies.exceed_cpu
        )


def test_children_are_spawned_never_forked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    methods: list[str | None] = []
    real = multiprocessing.get_context

    def spy(method: str | None = None) -> Any:
        methods.append(method)
        return real(method)

    monkeypatch.setattr("multiprocessing.get_context", spy)

    run_child(
        tmp_path / "m.glb", tmp_path / "o.webp", seconds=30, body=sandbox_bodies.report_limits
    )

    assert methods == ["spawn"]  # a fork would inherit the worker's threads and connections


def test_a_child_that_writes_no_preview_is_a_crash_retried_as_transient(tmp_path: Path) -> None:
    with pytest.raises(PreviewCrashedError, match="no preview"):
        run_child(
            tmp_path / "m.glb",
            tmp_path / "o.webp",
            seconds=30,
            body=sandbox_bodies.exit_without_writing,
        )


def test_a_child_that_crashes_otherwise_is_retried_as_transient(tmp_path: Path) -> None:
    with pytest.raises(PreviewCrashedError, match="exited with code 1"):
        run_child(tmp_path / "missing.glb", tmp_path / "out.webp", seconds=30)


def test_the_child_runs_under_its_own_limits(tmp_path: Path) -> None:
    target = tmp_path / "limits.txt"

    run_child(tmp_path / "m.glb", target, seconds=30, body=sandbox_bodies.report_limits)

    cpu, memory = (int(v) for v in target.read_text().split())
    assert cpu == MODEL_SANDBOX_CPU_SECONDS
    if sys.platform != "darwin":
        assert memory == MODEL_SANDBOX_MEMORY_BYTES


def test_a_memory_limit_that_cannot_be_set_on_linux_is_reported(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []

    def setrlimit(kind: int, limits: tuple[int, int]) -> None:
        calls.append((kind, limits))
        if kind == resource.RLIMIT_AS:
            raise ValueError("not allowed")

    monkeypatch.setattr("resource.setrlimit", setrlimit)
    monkeypatch.setattr("sys.platform", "linux")
    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        limit_child()

    assert calls == [
        (resource.RLIMIT_CPU, (MODEL_SANDBOX_CPU_SECONDS, MODEL_SANDBOX_CPU_SECONDS + 5)),
        (resource.RLIMIT_AS, (MODEL_SANDBOX_MEMORY_BYTES, MODEL_SANDBOX_MEMORY_BYTES)),
    ]
    assert "model preview runs without a memory limit (not allowed)" in caplog.text


def test_on_macos_the_missing_memory_limit_is_expected(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def setrlimit(kind: int, _limits: tuple[int, int]) -> None:
        if kind == resource.RLIMIT_AS:
            raise ValueError("not supported")

    monkeypatch.setattr("resource.setrlimit", setrlimit)
    monkeypatch.setattr("sys.platform", "darwin")
    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        limit_child()

    assert caplog.text == ""


def test_a_child_whose_worker_died_exits_by_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Parent:
        def is_alive(self) -> bool:
            return False

    exits: list[int] = []
    exited = threading.Event()

    def fake_exit(code: int) -> None:
        exits.append(code)
        exited.set()

    monkeypatch.setattr("multiprocessing.parent_process", _Parent)
    monkeypatch.setattr("os._exit", fake_exit)

    _watch_parent(every=0.01)

    assert exited.wait(2)
    assert exits == [4]


def test_the_default_body_maps_outcomes_to_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = tmp_path / "model.glb", tmp_path / "out.webp"
    source.write_bytes(b"glTF" + b"\x00" * 16)
    with pytest.raises(SystemExit) as unreadable:
        render_file(str(source), str(target))
    source.write_bytes(build_glb(tweak=lambda d: d["accessors"][1].update(count=3 * 2_000_001)))
    with pytest.raises(SystemExit) as too_large:
        render_file(str(source), str(target))

    def out_of_memory(_: bytes) -> object:
        raise MemoryError

    monkeypatch.setattr("kiln_worker.sandbox.read_glb", out_of_memory)
    with pytest.raises(SystemExit) as no_memory:
        render_file(str(source), str(target))

    assert (unreadable.value.code, too_large.value.code, no_memory.value.code) == (3, 4, 4)


def test_the_default_body_writes_the_preview(tmp_path: Path) -> None:
    source, target = tmp_path / "model.glb", tmp_path / "out.webp"
    source.write_bytes(build_glb())

    render_file(str(source), str(target))

    assert target.read_bytes()[:4] == b"RIFF"


def test_folders_left_by_a_killed_worker_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    old, young = tmp_path / "kiln-model-old", tmp_path / "kiln-model-young"
    other = tmp_path / "someone-else"
    for folder in (old, young, other):
        folder.mkdir()
        (folder / "model.glb").write_bytes(b"x")
    hour_ago = time.time() - 3600
    os.utime(old, (hour_ago, hour_ago))
    os.utime(other, (hour_ago, hour_ago))

    assert remove_stale_folders() == 1

    assert not old.exists()
    assert young.exists()
    assert other.exists()


def test_the_child_entry_sets_its_limits_and_watch_then_runs_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps: list[str] = []
    monkeypatch.setattr("kiln_worker.sandbox.limit_child", lambda: steps.append("limits"))
    monkeypatch.setattr("kiln_worker.sandbox._watch_parent", lambda: steps.append("watch"))

    _child_main(lambda source, target: steps.append(f"body {source} {target}"), "in", "out")

    assert steps == ["limits", "watch", "body in out"]


def test_watching_does_nothing_outside_a_spawned_child() -> None:
    before = threading.active_count()

    _watch_parent(every=0.01)  # pytest has no multiprocessing parent

    assert threading.active_count() == before


def test_a_child_keeps_watching_while_its_worker_lives(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([True, True, False])

    class _Parent:
        def is_alive(self) -> bool:
            return next(answers)

    exited = threading.Event()
    monkeypatch.setattr("multiprocessing.parent_process", _Parent)
    monkeypatch.setattr("os._exit", lambda _code: exited.set())

    _watch_parent(every=0.01)

    assert exited.wait(2)


_RENDER_SCRIPT = """
import io, sys
sys.path.insert(0, {tests!r})
from test_sandbox import _overdraw
from kiln_worker.sandbox import render_glb_sandboxed
print("rendering", flush=True)
render_glb_sandboxed(io.BytesIO(_overdraw(2_000_000)))
"""


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_render_child_stops_when_its_worker_is_killed_mid_render(tmp_path: Path) -> None:
    tests = str(Path(__file__).parent)
    worker = subprocess.Popen(  # noqa: S603 - our own code, fixed arguments
        [sys.executable, "-c", _RENDER_SCRIPT.format(tests=tests)],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
        # the killed worker cannot clean up: keep its model folder inside this test's tmp_path
        env={**os.environ, "PYTHONPATH": os.pathsep.join([*sys.path]), "TMPDIR": str(tmp_path)},
    )
    try:
        assert worker.stdout is not None
        assert worker.stdout.readline().strip() == "rendering"
        time.sleep(2)  # the child is drawing now
        worker.kill()  # SIGKILL: the worker cannot stop its child
        worker.wait(10)

        deadline = time.monotonic() + 10
        while _group_alive(worker.pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not _group_alive(worker.pid)  # the child noticed and exited by itself
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(worker.pid, signal.SIGKILL)
        worker.wait(10)
        if worker.stdout:
            worker.stdout.close()
