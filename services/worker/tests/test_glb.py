import json
import math
import struct
import time
from typing import Any

import numpy as np
import pytest
from glb_builder import CUBE_INDICES, assemble, build_glb

from kiln_worker import glb as glb_module
from kiln_worker.constants import MODEL_MAX_TRIANGLES, MODEL_MAX_VERTICES
from kiln_worker.errors import ModelTooLargeError, UnreadableModelError
from kiln_worker.glb import read_glb


def _bounds(data: bytes) -> tuple[list[float], list[float]]:
    mesh = read_glb(data)
    points = mesh.triangles.reshape(-1, 3) + mesh.origin  # back to scene coordinates
    return points.min(axis=0).round(4).tolist(), points.max(axis=0).round(4).tolist()


def test_a_cube_is_read_as_its_twelve_triangles() -> None:
    mesh = read_glb(build_glb())

    assert mesh.triangles.shape == (12, 3, 3)
    assert mesh.triangles.dtype == np.float32
    assert _bounds(build_glb()) == ([-1, -1, -1], [1, 1, 1])


@pytest.mark.parametrize("index_type", [5121, 5123, 5125])
def test_every_index_width_is_read(index_type: int) -> None:
    assert read_glb(build_glb(index_type=index_type)).triangles.shape == (12, 3, 3)


def test_a_primitive_without_indices_uses_its_vertices_in_order() -> None:
    triangle = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (5.0, 5.0, 5.0)]

    mesh = read_glb(build_glb(positions=triangle, indices=None))

    assert mesh.triangles.shape == (1, 3, 3)  # the incomplete fourth vertex is ignored


def _node(**fields: Any) -> Any:
    def tweak(document: dict[str, Any]) -> None:
        document["nodes"] = [{"mesh": 0, **fields}]

    return tweak


def test_translation_rotation_and_scale_are_applied() -> None:
    assert _bounds(build_glb(tweak=_node(translation=[10, 0, 0]))) == ([9, -1, -1], [11, 1, 1])
    assert _bounds(build_glb(tweak=_node(scale=[2, 1, 3]))) == ([-2, -1, -3], [2, 1, 3])
    half = math.sqrt(0.5)  # 90° about z: x becomes y
    rotated = build_glb(
        positions=[(0, 0, 0), (2, 0, 0), (0, 1, 0)],
        indices=None,
        tweak=_node(rotation=[0, 0, half, half]),
    )
    assert _bounds(rotated) == ([-1, 0, 0], [0, 2, 0])


def test_a_matrix_is_column_major() -> None:
    matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5, 6, 7, 1]  # translation in the last column

    assert _bounds(build_glb(tweak=_node(matrix=matrix))) == ([4, 5, 6], [6, 7, 8])


def test_nested_nodes_compose_their_transforms_and_meshes_can_be_instanced() -> None:
    def tweak(document: dict[str, Any]) -> None:
        document["nodes"] = [
            {"translation": [10, 0, 0], "children": [1, 2]},
            {"mesh": 0, "scale": [2, 2, 2]},
            {"mesh": 0, "translation": [0, 10, 0]},
        ]

    mesh = read_glb(build_glb(tweak=tweak))

    assert mesh.triangles.shape == (24, 3, 3)
    assert _bounds(build_glb(tweak=tweak)) == ([8, -2, -2], [12, 11, 2])


def test_without_scenes_the_root_nodes_are_drawn_and_without_nodes_the_meshes() -> None:
    def no_scenes(document: dict[str, Any]) -> None:
        del document["scenes"], document["scene"]
        document["nodes"] = [{"children": [1]}, {"mesh": 0, "translation": [3, 0, 0]}]

    def no_nodes(document: dict[str, Any]) -> None:
        del document["scenes"], document["scene"], document["nodes"]

    assert _bounds(build_glb(tweak=no_scenes)) == ([2, -1, -1], [4, 1, 1])
    assert read_glb(build_glb(tweak=no_nodes)).triangles.shape == (12, 3, 3)


def test_interleaved_positions_with_a_stride_are_read() -> None:
    positions = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    interleaved = b"".join(struct.pack("<3f3f", *p, 9, 9, 9) for p in positions)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(interleaved)}],
        "bufferViews": [{"buffer": 0, "byteLength": len(interleaved), "byteStride": 24}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }

    mesh = read_glb(assemble(document, interleaved))

    points = mesh.triangles.reshape(-1, 3) + mesh.origin
    assert points.round(4).tolist() == [[0, 0, 0], [1, 0, 0], [0, 1, 0]]


def test_points_and_lines_are_skipped() -> None:
    def add_lines(document: dict[str, Any]) -> None:
        primitives = document["meshes"][0]["primitives"]
        primitives.append({**primitives[0], "mode": 1})

    assert read_glb(build_glb(tweak=add_lines)).triangles.shape == (12, 3, 3)


def _set(path: str, value: Any) -> Any:
    def tweak(document: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        target: Any = document
        for key in parents:
            target = target[int(key)] if key.isdigit() else target[key]
        if value is _DELETE:
            del target[int(last) if last.isdigit() else last]
        else:
            target[int(last) if last.isdigit() else last] = value

    return tweak


_DELETE = object()


def _empty_positions(document: dict[str, Any]) -> None:
    document["accessors"][0]["count"] = 0
    del document["meshes"][0]["primitives"][0]["indices"]


@pytest.mark.parametrize(
    "tweak",
    [
        _set("extensionsRequired", ["KHR_draco_mesh_compression"]),
        _set("buffers.0.uri", "https://example.test/geometry.bin"),
        _set("buffers.0.byteLength", 10_000),
        _set("bufferViews.0.byteLength", 10_000),
        _set("bufferViews.0.byteOffset", 10_000),
        _set("bufferViews.0.byteStride", 8),
        _set("bufferViews.0.byteStride", 256),
        _set("accessors.0.count", 9),
        _set("accessors.0.byteOffset", 2),
        _set("accessors.0.componentType", 5123),
        _set("accessors.0.type", "VEC2"),
        _set("accessors.0.sparse", {"count": 1}),
        _set("accessors.0.bufferView", 7),
        _set("accessors.1.componentType", 5126),
        _set("accessors.1.count", -3),
        _set("meshes.0.primitives", "all of them"),
        _set("meshes.0.primitives.0.attributes.POSITION", 9),
        _set("nodes.0.mesh", 4),
        _set("nodes.0.mesh", True),
        _set("nodes.0.children", [0]),  # a cycle
        _set("nodes.0.matrix", [1, 0, 0]),
        _set("nodes.0.translation", [0, float("nan"), 0]),
        _set("nodes.0.rotation", ["a", 0, 0, 1]),
        _set("scene", 3),
        _set("scenes.0.nodes", {"0": 0}),
        _set("nodes", {"mesh": 0}),
        _set("meshes.0.primitives.0.mode", 0),  # nothing left to draw
        _set("meshes.0.primitives.0.attributes", {"NORMAL": 0}),  # no positions: nothing to draw
        _set("scenes.0", "the scene"),
        _set("nodes.0", 5),
        _set("nodes.0.children", "all"),
        _set("accessors.0", "positions"),
        _set("bufferViews.0", "view"),
        _empty_positions,
    ],
)
def test_broken_or_unsupported_models_are_refused(tweak: Any) -> None:
    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=tweak))


def test_an_index_past_the_last_vertex_is_refused() -> None:
    with pytest.raises(UnreadableModelError, match="index out of range"):
        read_glb(build_glb(indices=[*CUBE_INDICES[:-1], 8]))


@pytest.mark.parametrize(
    "data",
    [
        b"glTF",
        struct.pack("<III", 0x46546C67, 1, 12),
        struct.pack("<III", 0x46546C67, 2, 99),
        b"PK\x03\x04" + b"\x00" * 20,
        struct.pack("<III", 0x46546C67, 2, 16) + b"\x00" * 4,
        struct.pack("<IIIII", 0x46546C67, 2, 20, 99, 0x4E4F534A),
        assemble(b"[]"),
        assemble(b"{not json"),
        assemble(b"\xff\xfe"),
        struct.pack("<III", 0x46546C67, 2, 24) + struct.pack("<II", 4, 0x004E4942) + b"\x00" * 4,
    ],
)
def test_files_that_are_not_well_formed_glb_are_refused(data: bytes) -> None:
    with pytest.raises(UnreadableModelError):
        read_glb(data)


def test_too_many_triangles_are_refused_before_any_geometry_is_decoded() -> None:
    claimed = (MODEL_MAX_TRIANGLES + 1) * 3

    with pytest.raises(ModelTooLargeError):
        read_glb(build_glb(tweak=_set("accessors.1.count", claimed)))  # buffers are tiny


def test_instancing_counts_toward_the_triangle_limit() -> None:
    copies = MODEL_MAX_TRIANGLES // 12 + 1

    def many(document: dict[str, Any]) -> None:
        document["nodes"] = [{"children": list(range(1, copies + 1))}] + [{"mesh": 0}] * copies

    with pytest.raises(ModelTooLargeError):
        read_glb(build_glb(tweak=many))


def test_a_huge_json_chunk_is_refused_without_parsing_it() -> None:
    document = {"asset": {"version": "2.0"}, "padding": "x" * (16 * 1024 * 1024)}

    with pytest.raises(ModelTooLargeError, match="JSON chunk too large"):
        read_glb(assemble(json.dumps(document).encode()))


def test_a_very_deep_node_chain_is_refused() -> None:
    def deep(document: dict[str, Any]) -> None:
        document["nodes"] = [{"children": [i + 1]} for i in range(100)] + [{"mesh": 0}]

    with pytest.raises(UnreadableModelError, match="too deep"):
        read_glb(build_glb(tweak=deep))


def test_a_node_reached_twice_is_refused_however_the_graph_is_shaped() -> None:
    def shared(document: dict[str, Any]) -> None:
        document["nodes"] = [{"children": [1, 1]}, {"mesh": 0}]

    with pytest.raises(UnreadableModelError, match="reached twice"):
        read_glb(build_glb(tweak=shared))


def test_a_doubling_node_graph_is_refused_at_once() -> None:
    def doubling(document: dict[str, Any]) -> None:  # 2**40 paths if walked naively
        document["nodes"] = [{"children": [i + 1, i + 1]} for i in range(40)] + [{"mesh": 0}]
        document["scenes"] = [{"nodes": [0]}]

    started = time.monotonic()
    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=doubling))
    assert time.monotonic() - started < 1


def test_too_many_vertices_are_refused_before_decoding() -> None:
    with pytest.raises(ModelTooLargeError, match="vertices"):
        read_glb(build_glb(tweak=_set("accessors.0.count", MODEL_MAX_VERTICES + 1)))


def test_instances_decode_each_accessor_once(monkeypatch: pytest.MonkeyPatch) -> None:
    reads: list[int] = []
    real_read = glb_module._Reader._read

    def counting(self: Any, index: int, *args: Any) -> Any:
        reads.append(index)
        return real_read(self, index, *args)

    monkeypatch.setattr(glb_module._Reader, "_read", counting)

    def twenty(document: dict[str, Any]) -> None:
        document["nodes"] = [{"children": list(range(1, 21))}] + [
            {"mesh": 0, "translation": [i * 3, 0, 0]} for i in range(20)
        ]

    mesh = read_glb(build_glb(tweak=twenty))

    assert mesh.triangles.shape == (240, 3, 3)
    assert sorted(reads) == [0, 1]  # positions and indices, once each


@pytest.mark.parametrize(
    "document",
    [
        b"[" * 100_000 + b"]" * 100_000,  # nesting deeper than the parser allows
        b'{"asset": {"version": "2.0"}, "scene": ' + b"9" * 5000 + b"}",  # an absurd integer
        json.dumps({"nodes": [{"children": 5}]}).encode(),
        json.dumps({"nodes": [{"children": [[1]]}]}).encode(),
    ],
)
def test_malformed_structure_is_unreadable_not_a_crash(document: bytes) -> None:
    with pytest.raises(UnreadableModelError):
        read_glb(assemble(document))


def test_an_index_type_that_is_not_a_number_is_unreadable() -> None:
    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=_set("accessors.1.componentType", [1])))


def test_a_misaligned_accessor_offset_is_refused() -> None:
    def misaligned(document: dict[str, Any]) -> None:
        document["bufferViews"][0]["byteLength"] += 4  # room enough: only alignment is wrong
        document["accessors"][0]["byteOffset"] = 2

    with pytest.raises(UnreadableModelError, match="accessor runs past its bufferView"):
        read_glb(build_glb(tweak=misaligned))


def test_a_stride_that_is_not_a_multiple_of_the_component_size_is_refused() -> None:
    def odd_stride(document: dict[str, Any]) -> None:
        document["bufferViews"][0]["byteLength"] = 14 * 7 + 12  # room enough for the stride
        document["bufferViews"][0]["byteStride"] = 14

    with pytest.raises(UnreadableModelError, match="bad byteStride"):
        read_glb(build_glb(tweak=odd_stride))


def test_a_second_buffer_is_never_read() -> None:
    def second(document: dict[str, Any]) -> None:
        document["buffers"].append({"byteLength": 4})
        document["bufferViews"][0]["buffer"] = 1

    with pytest.raises(UnreadableModelError, match="only the embedded binary buffer"):
        read_glb(build_glb(tweak=second))


def test_a_small_model_far_from_the_origin_keeps_its_shape() -> None:
    def far(document: dict[str, Any]) -> None:
        document["nodes"] = [{"mesh": 0, "translation": [1e7, 0, 0], "scale": [0.01, 0.01, 0.01]}]

    mesh = read_glb(build_glb(tweak=far))

    points = mesh.triangles.reshape(-1, 3)
    assert np.ptp(points[:, 0]) == pytest.approx(0.02, rel=1e-3)  # float32 alone would lose it
    assert mesh.origin[0] == pytest.approx(1e7)


@pytest.mark.parametrize(
    "extension",
    [
        "KHR_texture_basisu",
        "EXT_texture_webp",
        "KHR_texture_transform",
        "KHR_materials_emissive_strength",
    ],
)
def test_required_extensions_that_leave_geometry_alone_are_accepted(extension: str) -> None:
    assert read_glb(build_glb(tweak=_set("extensionsRequired", [extension]))).triangles.shape == (
        12,
        3,
        3,
    )


@pytest.mark.parametrize("required", [["EXT_meshopt_compression"], "KHR_draco", [7]])
def test_other_required_extensions_are_refused(required: object) -> None:
    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=_set("extensionsRequired", required)))


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (5, [[0, 1, 2], [2, 1, 3], [2, 3, 4]]),  # strip: every other triangle flipped back
        (6, [[0, 1, 2], [0, 2, 3], [0, 3, 4]]),  # fan around the first vertex
    ],
)
def test_strips_and_fans_are_unrolled_into_triangles(mode: int, expected: list[list[int]]) -> None:
    positions = [(float(i), float(i * i), 0.0) for i in range(5)]

    def strip(document: dict[str, Any]) -> None:
        document["meshes"][0]["primitives"][0]["mode"] = mode

    mesh = read_glb(build_glb(positions=positions, indices=[0, 1, 2, 3, 4], tweak=strip))

    points = (mesh.triangles.reshape(-1, 3) + mesh.origin).round(4)
    vertex = {tuple(p): i for i, p in enumerate(np.array(positions))}
    assert [
        [vertex[tuple(p)] for p in triangle] for triangle in points.reshape(-1, 3, 3)
    ] == expected


def test_short_strips_and_fans_have_no_triangles() -> None:
    def two_vertex_strip(document: dict[str, Any]) -> None:
        document["meshes"][0]["primitives"][0]["mode"] = 5

    with pytest.raises(UnreadableModelError, match="no triangles"):
        read_glb(
            build_glb(positions=[(0, 0, 0), (1, 0, 0)], indices=[0, 1], tweak=two_vertex_strip)
        )
