import contextlib
import io
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from glb_builder import assemble, build_glb
from PIL import Image

from kiln_worker.constants import MODEL_SANDBOX_MEMORY_BYTES
from kiln_worker.errors import ModelTooLargeError, PreviewCrashedError, UnreadableModelError
from kiln_worker.sandbox import _limit_memory, _render_file, render_glb_sandboxed, run_child


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


def test_a_model_renders_in_the_child_process() -> None:
    preview = render_glb_sandboxed(build_glb())

    with Image.open(io.BytesIO(preview)) as image:
        assert (image.format, image.size) == ("WEBP", (512, 512))


def test_an_unreadable_model_is_reported_from_the_child() -> None:
    with pytest.raises(UnreadableModelError):
        render_glb_sandboxed(b"glTF" + b"\x00" * 16)


def test_a_model_over_its_geometry_budget_is_reported_from_the_child() -> None:
    with pytest.raises(ModelTooLargeError):
        render_glb_sandboxed(
            build_glb(tweak=lambda d: d["accessors"][1].update(count=3 * 2_000_001))
        )


def test_a_child_that_runs_too_long_is_killed_and_the_model_is_too_large() -> None:
    started = time.monotonic()

    with pytest.raises(ModelTooLargeError, match="preview took more than"):
        render_glb_sandboxed(_overdraw(1_000_000), seconds=1.0)

    assert time.monotonic() - started < 5  # killed: drawing alone would run for 20 s


def test_a_child_that_crashes_otherwise_is_retried_as_transient(tmp_path: Path) -> None:
    with pytest.raises(PreviewCrashedError, match="exited with code 1"):
        run_child(tmp_path / "missing.glb", tmp_path / "out.webp", seconds=30)


def test_the_child_asks_for_an_address_space_limit() -> None:
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    try:
        _limit_memory()  # enforced on Linux; refused or ignored on macOS without raising
        if sys.platform != "darwin":
            assert resource.getrlimit(resource.RLIMIT_AS)[0] == MODEL_SANDBOX_MEMORY_BYTES
    finally:
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_AS, (soft, hard))


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"glTF" + b"\x00" * 16, 3),
        (build_glb(tweak=lambda d: d["accessors"][1].update(count=3 * 2_000_001)), 4),
    ],
)
def test_the_child_body_exits_with_a_code_per_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: bytes, code: int
) -> None:
    monkeypatch.setattr("kiln_worker.sandbox._limit_memory", lambda: None)  # not in pytest
    source = tmp_path / "model.glb"
    source.write_bytes(data)

    with pytest.raises(SystemExit) as exited:
        _render_file(str(source), str(tmp_path / "out.webp"))

    assert exited.value.code == code


def test_the_child_body_writes_the_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kiln_worker.sandbox._limit_memory", lambda: None)
    source, target = tmp_path / "model.glb", tmp_path / "out.webp"
    source.write_bytes(build_glb())

    _render_file(str(source), str(target))

    assert target.read_bytes()[:4] == b"RIFF"
