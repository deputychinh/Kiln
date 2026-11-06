"""A defensive reader for glTF 2.0 binaries (KILN-5): triangles in world space, nothing else.

The file is untrusted. Every length, offset, stride, count and index is checked before use, no
URI is ever fetched, the node graph must be a strict tree (each node reached once), and the
triangle and vertex budgets are checked from accessor counts before anything is decoded. Each
accessor is decoded once, without copying the binary chunk. Any malformed structure — deep
JSON, absurd numbers, wrong types — is reported as an unreadable model.
Spec: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
"""

import json
import math
import struct
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from kiln_worker.constants import (
    MODEL_MAX_INSTANCES,
    MODEL_MAX_JSON_BYTES,
    MODEL_MAX_NODE_DEPTH,
    MODEL_MAX_TRIANGLES,
    MODEL_MAX_VERTICES,
)
from kiln_worker.errors import ModelTooLargeError, UnreadableModelError

_MAGIC = 0x46546C67  # "glTF"
_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942
_HEADER = struct.Struct("<III")
_CHUNK_HEADER = struct.Struct("<II")
_TRIANGLES, _TRIANGLE_STRIP, _TRIANGLE_FAN = 4, 5, 6
_FLOAT = 5126
_INDEX_TYPES: dict[int, np.dtype[Any]] = {
    5121: np.dtype("<u1"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
}
_MAX_STRIDE = 252
# Required extensions that change textures, materials or lights but never where vertices are.
# KHR_mesh_quantization is allowed too: its integer positions fail the float-only layout check.
_GEOMETRY_NEUTRAL_EXTENSIONS = frozenset(
    {
        "KHR_texture_basisu",
        "KHR_texture_transform",
        "EXT_texture_webp",
        "EXT_texture_avif",
        "KHR_lights_punctual",
        "KHR_mesh_quantization",
    }
)
_MALFORMED = (TypeError, ValueError, KeyError, IndexError, RecursionError, OverflowError)

type Matrix = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Mesh:
    """Triangles as an (n, 3, 3) float32 array of vertex positions.

    Positions are relative to a point of the model (not the scene origin), so float32 keeps
    its precision for georeferenced or CAD scenes far from the origin.
    """

    triangles: NDArray[np.float32]
    origin: NDArray[np.float64]  # add to `triangles` for scene coordinates


@dataclass(frozen=True, slots=True)
class _Primitive:
    positions: int  # accessor index
    indices: int | None
    mode: int


def read_glb(data: bytes) -> Mesh:
    """Read every triangle of the default scene, with node transforms applied."""
    try:
        return _read(data)
    except _MALFORMED as error:
        msg = f"malformed glTF ({type(error).__name__})"
        raise UnreadableModelError(msg) from error


def _read(data: bytes) -> Mesh:
    document, binary = _split(data)
    required = document.get("extensionsRequired", [])
    if not isinstance(required, list) or any(not _neutral(name) for name in required):
        msg = "required extensions are not supported"
        raise UnreadableModelError(msg)
    reader = _Reader(document, binary)
    instances = reader.instances()
    reader.check_budget(instances)
    parts = [reader.triangles(primitive, matrix) for primitive, matrix in instances]
    parts = [part for part in parts if len(part)]
    if not parts:
        msg = "no triangles"
        raise UnreadableModelError(msg)
    triangles = parts[0] if len(parts) == 1 else np.concatenate(parts)
    return Mesh(triangles=triangles, origin=reader.origin)


def _neutral(name: object) -> bool:
    return isinstance(name, str) and (
        name in _GEOMETRY_NEUTRAL_EXTENSIONS or name.startswith("KHR_materials_")
    )


def _split(data: bytes) -> tuple[dict[str, Any], memoryview]:
    if len(data) < _HEADER.size:
        msg = "shorter than a GLB header"
        raise UnreadableModelError(msg)
    magic, version, length = _HEADER.unpack_from(data)
    if magic != _MAGIC or version != 2 or length != len(data):  # noqa: PLR2004 - glTF 2
        msg = "not a glTF 2.0 binary"
        raise UnreadableModelError(msg)
    chunks = _chunks(memoryview(data), length)
    if not chunks or chunks[0][0] != _JSON_CHUNK:
        msg = "the first chunk must be JSON"
        raise UnreadableModelError(msg)
    document = json.loads(bytes(chunks[0][1]))  # deep nesting or huge numbers: malformed
    if not isinstance(document, dict):
        msg = "JSON is not an object"
        raise UnreadableModelError(msg)
    binary = chunks[1][1] if len(chunks) > 1 and chunks[1][0] == _BIN_CHUNK else memoryview(b"")
    return document, binary


def _chunks(data: memoryview, length: int) -> list[tuple[int, memoryview]]:
    """The (type, bytes) chunks after the header, each checked against the file length."""
    chunks: list[tuple[int, memoryview]] = []
    offset = _HEADER.size
    while offset < length:
        if offset + _CHUNK_HEADER.size > length:
            msg = "truncated chunk header"
            raise UnreadableModelError(msg)
        size, kind = _CHUNK_HEADER.unpack_from(data, offset)
        start = offset + _CHUNK_HEADER.size
        if size > length - start:
            msg = "chunk runs past the end"
            raise UnreadableModelError(msg)
        if kind == _JSON_CHUNK and size > MODEL_MAX_JSON_BYTES:
            msg = "JSON chunk too large"
            raise ModelTooLargeError(msg)
        chunks.append((kind, data[start : start + size]))
        offset = start + size
    return chunks


def _fail(what: str) -> UnreadableModelError:
    return UnreadableModelError(what)


def _items(document: dict[str, Any], name: str) -> list[Any]:
    value = document.get(name, [])
    if not isinstance(value, list):
        msg = f"{name} is not a list"
        raise _fail(msg)
    return value


def _index(value: object, items: list[Any], what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < len(items):
        msg = f"bad {what} index"
        raise _fail(msg)
    return value


def _non_negative(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = f"bad {what}"
        raise _fail(msg)
    return value


def _triangles_in(count: int, mode: int) -> int:
    return count // 3 if mode == _TRIANGLES else max(count - 2, 0)


class _Reader:
    """Resolves nodes, meshes, accessors and buffer views, checking each against the binary."""

    def __init__(self, document: dict[str, Any], binary: memoryview) -> None:
        self._doc = document
        self._binary = binary
        self._nodes = _items(document, "nodes")
        self._meshes = _items(document, "meshes")
        self._accessors = _items(document, "accessors")
        self._views = _items(document, "bufferViews")
        self._buffers = _items(document, "buffers")
        self._decoded: dict[int, NDArray[Any]] = {}
        self._origin: NDArray[np.float64] | None = None

    def instances(self) -> list[tuple[_Primitive, Matrix]]:
        """Every triangle primitive of the default scene with its world matrix."""
        found: list[tuple[_Primitive, Matrix]] = []
        visited: set[int] = set()
        for root in self._roots():
            self._walk(root, np.identity(4), 0, found, visited)
        if not self._nodes:  # meshes without a scene graph
            for mesh in range(len(self._meshes)):
                found.extend((p, np.identity(4)) for p in self._primitives(mesh))
        return found

    def _children(self, node: object) -> list[int]:
        if not isinstance(node, dict):
            msg = "node is not an object"
            raise _fail(msg)
        children = node.get("children", [])
        if not isinstance(children, list):
            msg = "children is not a list"
            raise _fail(msg)
        return [_index(child, self._nodes, "node") for child in children]

    def _roots(self) -> list[int]:
        scenes = _items(self._doc, "scenes")
        if scenes:
            scene = scenes[_index(self._doc.get("scene", 0), scenes, "scene")]
            if not isinstance(scene, dict):
                msg = "scene is not an object"
                raise _fail(msg)
            nodes = scene.get("nodes", [])
            if not isinstance(nodes, list):
                msg = "scene nodes are not a list"
                raise _fail(msg)
            return [_index(n, self._nodes, "node") for n in nodes]
        children = {c for node in self._nodes for c in self._children(node)}
        return [i for i in range(len(self._nodes)) if i not in children]

    def _walk(
        self,
        index: int,
        parent: Matrix,
        depth: int,
        found: list[tuple[_Primitive, Matrix]],
        visited: set[int],
    ) -> None:
        if index in visited:  # glTF nodes form disjoint trees: shared children or cycles
            msg = "a node is reached twice"
            raise _fail(msg)
        visited.add(index)
        if depth > MODEL_MAX_NODE_DEPTH:
            msg = "node hierarchy too deep"
            raise _fail(msg)
        node = self._nodes[index]
        children = self._children(node)
        matrix = parent @ _local_matrix(node)
        if "mesh" in node:
            mesh = _index(node["mesh"], self._meshes, "mesh")
            found.extend((p, matrix) for p in self._primitives(mesh))
            if len(found) > MODEL_MAX_INSTANCES:
                msg = "too many mesh instances"
                raise ModelTooLargeError(msg)
        for child in children:
            self._walk(child, matrix, depth + 1, found, visited)

    def _primitives(self, mesh: int) -> list[_Primitive]:
        entry = self._meshes[mesh]
        primitives = entry.get("primitives", []) if isinstance(entry, dict) else None
        if not isinstance(primitives, list):
            msg = "primitives is not a list"
            raise _fail(msg)
        result: list[_Primitive] = []
        for primitive in primitives:
            mode = primitive.get("mode", _TRIANGLES) if isinstance(primitive, dict) else None
            if mode not in {_TRIANGLES, _TRIANGLE_STRIP, _TRIANGLE_FAN}:
                continue  # points and lines are not drawn
            attributes = primitive.get("attributes", {})
            if not isinstance(attributes, dict) or "POSITION" not in attributes:
                continue
            positions = _index(attributes["POSITION"], self._accessors, "accessor")
            indices = primitive.get("indices")
            result.append(
                _Primitive(
                    positions=positions,
                    indices=None
                    if indices is None
                    else _index(indices, self._accessors, "accessor"),
                    mode=int(mode),
                )
            )
        return result

    def check_budget(self, instances: list[tuple[_Primitive, Matrix]]) -> None:
        """Refuse too much geometry from accessor counts alone, before decoding anything."""
        triangles = 0
        for primitive, _ in instances:
            counted = primitive.indices if primitive.indices is not None else primitive.positions
            count = _non_negative(self._accessor(counted).get("count"), "count")
            triangles += _triangles_in(count, primitive.mode)
        vertices = sum(
            _non_negative(self._accessor(a).get("count"), "count")
            for a in {primitive.positions for primitive, _ in instances}
        )
        if triangles > MODEL_MAX_TRIANGLES or vertices > MODEL_MAX_VERTICES:
            msg = f"{triangles} triangles, {vertices} vertices"
            raise ModelTooLargeError(msg)

    def triangles(self, primitive: _Primitive, matrix: Matrix) -> NDArray[np.float32]:
        """Triangles of one primitive instance, as (n, 3, 3), relative to the model origin."""
        positions = self._positions(primitive.positions)
        corners = self._corners(primitive, len(positions))
        if not len(corners):
            return np.zeros((0, 3, 3), dtype=np.float32)
        used, inverse = np.unique(corners, return_inverse=True)  # transform used vertices only
        world = positions[used].astype(np.float64) @ matrix[:3, :3].T + matrix[:3, 3]
        if self._origin is None:
            self._origin = world.mean(axis=0)
        local = (world - self._origin).astype(np.float32)
        return local[inverse].reshape(-1, 3, 3)

    @property
    def origin(self) -> NDArray[np.float64]:
        """The point triangles are relative to (the first instance's centre)."""
        return np.zeros(3) if self._origin is None else self._origin

    def _positions(self, accessor: int) -> NDArray[np.float32]:
        if accessor not in self._decoded:
            self._decoded[accessor] = self._read(accessor, _FLOAT, 3, np.dtype("<f4"))
        return self._decoded[accessor]

    def _corners(self, primitive: _Primitive, vertices: int) -> NDArray[np.int64]:
        """Vertex indices, three per triangle (strips and fans unrolled), checked in range."""
        if primitive.indices is None:
            corners = np.arange(vertices, dtype=np.int64)
        else:
            if primitive.indices not in self._decoded:
                accessor = self._accessor(primitive.indices)
                component = accessor.get("componentType")
                dtype = _INDEX_TYPES.get(component) if isinstance(component, int) else None
                if dtype is None or not isinstance(component, int):
                    msg = "bad index type"
                    raise _fail(msg)
                read = self._read(primitive.indices, component, 1, dtype).reshape(-1)
                self._decoded[primitive.indices] = read.astype(np.int64)
            corners = self._decoded[primitive.indices]
            if len(corners) and int(corners.max()) >= vertices:
                msg = "index out of range"
                raise _fail(msg)
        if primitive.mode == _TRIANGLE_STRIP:
            return _unroll_strip(corners)
        if primitive.mode == _TRIANGLE_FAN:
            return _unroll_fan(corners)
        return corners[: len(corners) - len(corners) % 3]

    def _accessor(self, index: int) -> dict[str, Any]:
        accessor = self._accessors[index]
        if not isinstance(accessor, dict):
            msg = "accessor is not an object"
            raise _fail(msg)
        if "sparse" in accessor:
            msg = "sparse accessors are not supported"
            raise _fail(msg)
        return accessor

    def _read(self, index: int, component: int, width: int, dtype: np.dtype[Any]) -> NDArray[Any]:
        accessor = self._accessor(index)
        expected_type = "VEC3" if width == 3 else "SCALAR"  # noqa: PLR2004 - positions
        if accessor.get("componentType") != component or accessor.get("type") != expected_type:
            msg = "unexpected accessor layout"
            raise _fail(msg)
        count = _non_negative(accessor.get("count"), "count")
        if count == 0:
            return np.zeros((0, width), dtype=dtype)
        view = self._views[_index(accessor.get("bufferView"), self._views, "bufferView")]
        if not isinstance(view, dict):
            msg = "bufferView is not an object"
            raise _fail(msg)
        buffer = self._buffer(_index(view.get("buffer"), self._buffers, "buffer"))
        view_offset = _non_negative(view.get("byteOffset", 0), "byteOffset")
        view_length = _non_negative(view.get("byteLength"), "byteLength")
        if view_offset + view_length > len(buffer):
            msg = "bufferView runs past its buffer"
            raise _fail(msg)
        element = dtype.itemsize * width
        stride = _non_negative(view.get("byteStride", element), "byteStride")
        if stride < element or stride > _MAX_STRIDE or stride % dtype.itemsize:
            msg = "bad byteStride"
            raise _fail(msg)
        offset = _non_negative(accessor.get("byteOffset", 0), "byteOffset")
        if offset % dtype.itemsize or offset + stride * (count - 1) + element > view_length:
            msg = "accessor runs past its bufferView"
            raise _fail(msg)
        values = np.ndarray(
            shape=(count, width),
            dtype=dtype,
            buffer=buffer,
            offset=view_offset + offset,
            strides=(stride, dtype.itemsize),
        )
        return values.copy()  # only this accessor's elements, not the whole buffer

    def _buffer(self, index: int) -> memoryview:
        buffer = self._buffers[index]
        if not isinstance(buffer, dict) or "uri" in buffer or index != 0:
            msg = "only the embedded binary buffer is read"
            raise _fail(msg)
        length = _non_negative(buffer.get("byteLength"), "byteLength")
        if length > len(self._binary):
            msg = "buffer longer than the binary chunk"
            raise _fail(msg)
        return self._binary[:length]  # a view: no copy


def _unroll_strip(corners: NDArray[np.int64]) -> NDArray[np.int64]:
    """Triangle strip to a triangle list, keeping a consistent winding."""
    count = len(corners) - 2
    if count <= 0:
        return np.zeros(0, dtype=np.int64)
    first, second, third = corners[:-2], corners[1:-1], corners[2:]
    odd = np.arange(count) % 2 == 1
    return np.stack(
        [np.where(odd, second, first), np.where(odd, first, second), third], axis=1
    ).reshape(-1)


def _unroll_fan(corners: NDArray[np.int64]) -> NDArray[np.int64]:
    """Triangle fan to a triangle list."""
    count = len(corners) - 2
    if count <= 0:
        return np.zeros(0, dtype=np.int64)
    hub = np.full(count, corners[0])
    return np.stack([hub, corners[1:-1], corners[2:]], axis=1).reshape(-1)


def _local_matrix(node: dict[str, Any]) -> Matrix:
    """A node's local transform: `matrix` (column-major) or translation * rotation * scale."""
    if "matrix" in node:
        values = _numbers(node["matrix"], 16, "matrix")
        return np.array(values, dtype=np.float64).reshape(4, 4).T
    tx, ty, tz = _numbers(node.get("translation", [0, 0, 0]), 3, "translation")
    x, y, z, w = _numbers(node.get("rotation", [0, 0, 0, 1]), 4, "rotation")
    sx, sy, sz = _numbers(node.get("scale", [1, 1, 1]), 3, "scale")
    norm = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    matrix = np.identity(4)
    matrix[:3, :3] = rotation * np.array([sx, sy, sz])
    matrix[:3, 3] = [tx, ty, tz]
    return matrix


def _numbers(value: object, count: int, what: str) -> list[float]:
    if (
        not isinstance(value, list)
        or len(value) != count
        or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in value)
        or not all(math.isfinite(v) for v in value)
    ):
        msg = f"bad {what}"
        raise _fail(msg)
    return [float(v) for v in value]
