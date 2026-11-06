import contextlib
import io
import time
from typing import Any

import numpy as np
import pytest
from glb_builder import build_glb
from PIL import Image

from kiln_worker.errors import UnreadableModelError
from kiln_worker.glb import Mesh, read_glb
from kiln_worker.model_preview import _rotation, render_model


def _image(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def test_a_cube_renders_as_a_shaded_preview_on_a_transparent_background() -> None:
    image = _image(render_model(read_glb(build_glb())))

    assert (image.format, image.size, image.mode) == ("WEBP", (512, 512), "RGBA")
    pixels = np.asarray(image)
    assert pixels[2, 2, 3] == 0  # transparent corner
    assert pixels[256, 256, 3] == 255  # the model fills the centre
    opaque = pixels[pixels[:, :, 3] == 255]
    shades = set((opaque[:, 0] // 16).tolist())
    assert len(shades) >= 3  # three visible faces, each lit differently


def _faces(pixels: np.ndarray) -> dict[int, float]:
    """Shade bucket -> mean row of each face covering at least 2 % of the silhouette."""
    opaque = pixels[:, :, 3] == 255
    buckets = pixels[:, :, 0] // 8
    values, counts = np.unique(buckets[opaque], return_counts=True)
    return {
        int(v): float(np.nonzero(opaque & (buckets == v))[0].mean())
        for v, c in zip(values, counts, strict=True)
        if c > opaque.sum() * 0.02
    }


def test_a_box_is_seen_from_above_with_the_top_face_brightest() -> None:
    def tall(document: dict[str, Any]) -> None:
        document["nodes"] = [{"mesh": 0, "scale": [1, 2, 1]}]

    faces = _faces(np.asarray(_image(render_model(read_glb(build_glb(tweak=tall))))))

    assert len(faces) == 3
    brightest = max(faces)
    assert faces[brightest] == min(faces.values())  # the brightest face is the top one


def test_back_faces_never_show_through_a_closed_box() -> None:
    def slab(document: dict[str, Any]) -> None:  # a shape where depth sorting alone fails
        document["nodes"] = [
            {"mesh": 0, "scale": [0.2, 4.0, 1.0], "rotation": [-0.0672, -0.2509, 0.9635, 0.0655]}
        ]

    mesh = read_glb(build_glb(tweak=slab))
    view = mesh.triangles @ _rotation().T.astype(np.float32)
    edge_a, edge_b = view[:, 1] - view[:, 0], view[:, 2] - view[:, 0]
    front = edge_a[:, 0] * edge_b[:, 1] - edge_a[:, 1] * edge_b[:, 0] >= 0
    culled = Mesh(
        origin=np.zeros(3), triangles=mesh.triangles[front]
    )  # the right answer for a convex solid

    full = np.asarray(_image(render_model(mesh))).astype(int)
    expected = np.asarray(_image(render_model(culled))).astype(int)

    assert (np.abs(full - expected).max(axis=2) > 40).mean() < 0.001


def test_the_model_is_fitted_to_the_frame_whatever_its_size() -> None:
    tiny = Mesh(
        origin=np.zeros(3), triangles=(read_glb(build_glb()).triangles * 0.001).astype(np.float32)
    )
    image = _image(render_model(tiny))

    box = image.getchannel("A").getbbox()
    assert box is not None
    width, height = box[2] - box[0], box[3] - box[1]
    assert max(width, height) > 400  # about 86 % of 512


def test_non_finite_vertices_are_dropped_and_nothing_drawable_is_refused() -> None:
    cube = read_glb(build_glb()).triangles.copy()
    cube[0, 0, 0] = np.inf
    assert _image(render_model(Mesh(origin=np.zeros(3), triangles=cube))).size == (512, 512)

    with pytest.raises(UnreadableModelError):
        render_model(
            Mesh(origin=np.zeros(3), triangles=np.full((2, 3, 3), np.nan, dtype=np.float32))
        )
    flat = np.zeros((4, 3, 3), dtype=np.float32)  # zero-area triangles only
    with pytest.raises(UnreadableModelError):
        render_model(Mesh(origin=np.zeros(3), triangles=flat))


def test_dense_meshes_render_within_the_time_budget() -> None:
    rng = np.random.default_rng(7)
    centres = rng.uniform(-1, 1, size=(200_000, 1, 3))
    triangles = (centres + rng.normal(0, 0.002, size=(200_000, 3, 3))).astype(np.float32)

    started = time.monotonic()
    image = _image(render_model(Mesh(origin=np.zeros(3), triangles=triangles)))

    assert time.monotonic() - started < 5
    assert image.getchannel("A").getbbox() is not None


@pytest.mark.parametrize("scale", [1e19, 1e38])
def test_coordinates_near_the_float_limit_never_warn(scale: float) -> None:
    huge = (read_glb(build_glb()).triangles * np.float32(scale)).astype(np.float32)

    # filterwarnings=error turns any overflow warning into a failure here
    with contextlib.suppress(UnreadableModelError):
        render_model(Mesh(origin=np.zeros(3), triangles=huge))
