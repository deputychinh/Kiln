"""A still preview of a 3D model (KILN-5): flat-shaded, three-quarter view, no GPU needed."""

import io
import math

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from kiln_worker.constants import (
    MODEL_FILL_RATIO,
    MODEL_PITCH_DEGREES,
    MODEL_SUPERSAMPLE,
    MODEL_YAW_DEGREES,
    THUMBNAIL_MAX_SIDE,
    THUMBNAIL_QUALITY,
)
from kiln_worker.errors import UnreadableModelError
from kiln_worker.glb import Mesh

_SURFACE = np.array([196.0, 198.0, 204.0])  # neutral, slightly cool grey
_AMBIENT = 0.30
_KEY = np.array([-0.45, 0.65, 0.62])  # upper left, towards the viewer
_KEY_WEIGHT = 0.6
_FILL = np.array([0.8, 0.15, 0.35])  # from the right, so no side goes black
# A box's three visible faces come out at about 86 %, 62 % and 41 % of the surface colour.
_FILL_WEIGHT = 0.15
_SUBPIXEL_AREA = 0.5
_CHUNK = 65_536


def _rotation() -> NDArray[np.float64]:
    yaw, pitch = math.radians(MODEL_YAW_DEGREES), math.radians(MODEL_PITCH_DEGREES)
    turn = np.array(
        [[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]]
    )
    tilt = np.array(
        [[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]]
    )
    return np.asarray(tilt @ turn, dtype=np.float64)


def render_model(mesh: Mesh) -> bytes:
    """See `_render`; extreme coordinates overflow to inf/nan quietly and are dropped there."""
    with np.errstate(over="ignore", invalid="ignore"):
        return _render(mesh)


def _render(mesh: Mesh) -> bytes:
    """A 512 x 512 WebP with a transparent background, the model fitted to the frame.

    Memory stays near three float32 copies of the triangles: the view transform and the
    back-to-front order are global, shading and drawing go chunk by chunk.
    """
    triangles = mesh.triangles[np.isfinite(mesh.triangles).all(axis=(1, 2))]
    if not len(triangles):
        msg = "no finite triangles"
        raise UnreadableModelError(msg)
    view = triangles @ _rotation().T.astype(np.float32)  # looks down -z; +z faces the viewer
    del triangles
    size = THUMBNAIL_MAX_SIDE * MODEL_SUPERSAMPLE
    low, high = view.min(axis=(0, 1)), view.max(axis=(0, 1))
    extent = max(float(high[0] - low[0]), float(high[1] - low[1])) or 1.0
    scale = np.float32(size * MODEL_FILL_RATIO / extent)
    centre = ((low + high) / 2).astype(np.float32)

    edge_a, edge_b = view[:, 1] - view[:, 0], view[:, 2] - view[:, 0]
    facing = edge_a[:, 0] * edge_b[:, 1] - edge_a[:, 1] * edge_b[:, 0] >= 0  # normal z
    del edge_a, edge_b
    # Back faces first, then front faces, each far to near: a closed model's front always covers
    # its back (centre-depth sorting alone lets long back faces poke through), and the inside
    # of an open surface still shows where nothing is in front of it.
    order = np.lexsort((view[:, :, 2].mean(axis=1), facing))

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    drawn = 0
    for start in range(0, len(order), _CHUNK):
        chunk = view[order[start : start + _CHUNK]]
        drawn += _draw(draw, chunk, centre=centre, scale=scale, size=size)
    if not drawn:
        msg = "every triangle has zero area"
        raise UnreadableModelError(msg)
    preview = canvas.resize((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    preview.save(out, "WEBP", quality=THUMBNAIL_QUALITY)
    return out.getvalue()


def _draw(
    draw: ImageDraw.ImageDraw,
    chunk: NDArray[np.float32],
    *,
    centre: NDArray[np.float32],
    scale: np.float32,
    size: int,
) -> int:
    """Shade and draw one chunk of view-space triangles in order; returns how many were drawn."""
    normals = np.cross(chunk[:, 1] - chunk[:, 0], chunk[:, 2] - chunk[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    keep = lengths > 0
    chunk, normals = chunk[keep], normals[keep] / lengths[keep, None]
    normals[normals[:, 2] < 0] *= -1  # double-sided: light whichever side faces the camera
    key, fill = _KEY / np.linalg.norm(_KEY), _FILL / np.linalg.norm(_FILL)
    shade = np.clip(
        _AMBIENT
        + _KEY_WEIGHT * np.clip(normals @ key, 0, 1)
        + _FILL_WEIGHT * np.clip(normals @ fill, 0, 1),
        0,
        1,
    )
    colours = np.clip(shade[:, None] * _SURFACE, 0, 255).astype(np.uint8)
    xs = (chunk[:, :, 0] - centre[0]) * scale + size / 2
    ys = size / 2 - (chunk[:, :, 1] - centre[1]) * scale
    areas = (
        np.abs(
            (xs[:, 1] - xs[:, 0]) * (ys[:, 2] - ys[:, 0])
            - (xs[:, 2] - xs[:, 0]) * (ys[:, 1] - ys[:, 0])
        )
        / 2
    )
    for x, y, colour, area in zip(
        xs.tolist(), ys.tolist(), colours.tolist(), areas.tolist(), strict=True
    ):
        fill_colour = (colour[0], colour[1], colour[2], 255)
        if area < _SUBPIXEL_AREA:
            draw.point((sum(x) / 3, sum(y) / 3), fill=fill_colour)
        else:
            draw.polygon(list(zip(x, y, strict=True)), fill=fill_colour)
    return len(chunk)
