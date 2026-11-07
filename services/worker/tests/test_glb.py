import json
import math
import struct
import time
import tracemalloc
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from glb_builder import (
    CUBE_INDICES,
    add_doubling_chain,
    assemble,
    build_glb,
    cycle_in_a_second_scene,
    dag_in_a_second_scene,
    dag_in_the_default_scene,
)

from kiln_worker import glb as glb_module
from kiln_worker.constants import (
    MODEL_MAX_ACCESSOR_ELEMENTS,
    MODEL_MAX_OBJECTS,
    MODEL_MAX_TRIANGLES,
    MODEL_MAX_VERTICES,
)
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


def test_chunks_after_json_and_bin_are_never_read() -> None:
    cube = build_glb()
    junk = struct.pack("<II", 0, 0x12345678) * 1_000_000  # a million empty chunks
    data = struct.pack("<III", 0x46546C67, 2, len(cube) + len(junk)) + cube[12:] + junk

    tracemalloc.start()
    try:
        mesh = read_glb(data)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert mesh.triangles.shape == (12, 3, 3)
    assert peak < 5 * 1024 * 1024  # a view per chunk would hold hundreds of MB


def test_a_chunk_longer_than_the_file_is_refused() -> None:
    cube = build_glb()
    json_size = struct.unpack_from("<I", cube, 12)[0]
    lying = bytearray(cube)
    struct.pack_into("<I", lying, 12, json_size + 1_000)  # JSON chunk claims more than exists

    with pytest.raises(UnreadableModelError, match="chunk runs past the end"):
        read_glb(bytes(lying))


@pytest.mark.parametrize("name", ["nodes", "meshes", "accessors", "bufferViews", "scenes"])
def test_overlong_object_lists_are_refused_as_too_large(name: str) -> None:
    def overlong(document: dict[str, Any]) -> None:
        document[name] = [{}] * (MODEL_MAX_OBJECTS + 1)

    with pytest.raises(ModelTooLargeError, match=name):
        read_glb(build_glb(tweak=overlong))


def test_a_stride_above_the_gltf_maximum_is_refused() -> None:
    def wide(document: dict[str, Any]) -> None:
        document["bufferViews"][0]["byteLength"] = 256 * 7 + 12
        document["bufferViews"][0]["byteStride"] = 256
        document["buffers"][0]["byteLength"] = 256 * 7 + 12

    with pytest.raises(UnreadableModelError, match="bad byteStride"):
        read_glb(build_glb(tweak=wide, binary_padding=256 * 7 + 12))


def test_more_instances_than_allowed_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(glb_module, "MODEL_MAX_INSTANCES", 2)

    def three(document: dict[str, Any]) -> None:
        document["nodes"] = [{"children": [1, 2, 3]}, {"mesh": 0}, {"mesh": 0}, {"mesh": 0}]

    with pytest.raises(ModelTooLargeError, match="instances"):
        read_glb(build_glb(tweak=three))


def test_more_instances_than_allowed_without_nodes_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(glb_module, "MODEL_MAX_INSTANCES", 2)

    def three_meshes(document: dict[str, Any]) -> None:
        del document["scenes"], document["scene"], document["nodes"]
        document["meshes"] = document["meshes"] * 3

    with pytest.raises(ModelTooLargeError, match="instances"):
        read_glb(build_glb(tweak=three_meshes))


def test_rotations_are_normalised_before_use() -> None:
    half = math.sqrt(0.5)
    unit = _bounds(build_glb(tweak=_node(rotation=[0, 0, half, half])))
    scaled = _bounds(build_glb(tweak=_node(rotation=[0, 0, 3.0, 3.0])))  # same rotation, length 4.2

    assert scaled == unit


def test_counts_must_be_integers_not_booleans() -> None:
    with pytest.raises(UnreadableModelError, match="bad count"):
        read_glb(build_glb(tweak=_set("accessors.1.count", True)))


def test_required_quantization_is_accepted_when_positions_are_floats() -> None:
    mesh = read_glb(build_glb(tweak=_set("extensionsRequired", ["KHR_mesh_quantization"])))

    assert mesh.triangles.shape == (12, 3, 3)


def test_a_fan_of_two_vertices_has_no_triangles() -> None:
    def fan(document: dict[str, Any]) -> None:
        document["meshes"][0]["primitives"][0]["mode"] = 6

    with pytest.raises(UnreadableModelError, match="no triangles"):
        read_glb(build_glb(positions=[(0, 0, 0), (1, 0, 0)], indices=[0, 1], tweak=fan))


def test_a_mesh_used_by_many_nodes_resolves_its_primitives_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved: list[int] = []
    real = glb_module._Reader._resolve_primitives

    def counting(self: Any, mesh: int) -> Any:
        resolved.append(mesh)
        return real(self, mesh)

    monkeypatch.setattr(glb_module._Reader, "_resolve_primitives", counting)

    def busy(document: dict[str, Any]) -> None:
        document["meshes"][0]["primitives"] += [{}] * 99_999
        document["nodes"] = [{"children": list(range(1, 201))}] + [{"mesh": 0}] * 200

    mesh = read_glb(build_glb(tweak=busy))

    assert mesh.triangles.shape == (2400, 3, 3)
    assert resolved == [0]  # 100,000 entries walked once, not once per node


def test_too_many_primitives_in_one_mesh_are_refused() -> None:
    def crowded(document: dict[str, Any]) -> None:
        document["meshes"][0]["primitives"] += [{}] * MODEL_MAX_OBJECTS

    with pytest.raises(ModelTooLargeError, match="primitives in one mesh"):
        read_glb(build_glb(tweak=crowded))


@pytest.mark.parametrize("swap", ["indices_as_positions", "positions_as_indices"])
def test_an_accessor_used_in_two_roles_is_refused(swap: str) -> None:
    def mixed(document: dict[str, Any]) -> None:
        primitive = document["meshes"][0]["primitives"][0]
        extra = {**primitive}
        if swap == "indices_as_positions":
            extra["attributes"] = {"POSITION": 1}
            del extra["indices"]
        else:
            extra["indices"] = 0
        document["meshes"][0]["primitives"].append(extra)

    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=mixed))


def test_an_overflowing_first_instance_does_not_spoil_the_others() -> None:
    def first_explodes(document: dict[str, Any]) -> None:
        document["nodes"] = [
            {"children": [1, 2]},
            {"mesh": 0, "scale": [1e308, 1e308, 1e308]},
            {"mesh": 0},
        ]

    mesh = read_glb(build_glb(tweak=first_explodes))

    finite = np.isfinite(mesh.triangles).all(axis=(1, 2))
    assert finite.sum() == 12  # the ordinary cube survives


# KILN-9 review: the browser viewer reads every accessor of a ready file, so the worker must check
# all of them, not only the ones its preview draws.
_CRATE = Path(__file__).resolve().parents[3] / "apps/web/e2e/fixtures/crate.glb"


def _colour_bomb() -> bytes:
    """The review's 768-byte proof of concept: a COLOR_0 of 200,000,000 VEC4 with no bufferView."""
    data = _CRATE.read_bytes()
    (length,) = struct.unpack_from("<I", data, 12)
    document = json.loads(data[20 : 20 + length])
    binary = data[20 + length + 8 :]
    document["accessors"].append({"componentType": 5126, "count": 200_000_000, "type": "VEC4"})
    document["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"] = 2
    return assemble(json.dumps(document, separators=(",", ":")).encode(), binary)


def test_the_768_byte_colour_accessor_bomb_is_refused_without_allocating() -> None:
    bomb = _colour_bomb()
    assert len(bomb) == 768
    tracemalloc.start()
    try:
        with pytest.raises(UnreadableModelError):
            read_glb(bomb)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 5 * 1024 * 1024


def _add_accessor(accessor: dict[str, Any]) -> Any:
    def tweak(document: dict[str, Any]) -> None:
        document["accessors"].append(accessor)

    return tweak


@pytest.mark.parametrize(
    "accessor",
    [
        pytest.param({"componentType": 5126, "count": 8, "type": "VEC3"}, id="no bufferView"),
        pytest.param(
            {"bufferView": 0, "componentType": 5126, "count": 9, "type": "VEC3"},
            id="one element past its view",
        ),
        pytest.param(
            {"bufferView": 0, "byteOffset": 4, "componentType": 5126, "count": 8, "type": "VEC3"},
            id="pushed past its view by its offset",
        ),
        pytest.param(
            {"bufferView": 0, "componentType": 5126, "count": 2, "type": "MAT4"},
            id="a matrix larger than its view",
        ),
        pytest.param(
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 2,
                "type": "VEC3",
                "sparse": {"count": 1},
            },
            id="sparse",
        ),
        pytest.param(
            {"bufferView": 0, "componentType": 5124, "count": 1, "type": "SCALAR"}, id="int32"
        ),
        pytest.param(
            {"bufferView": 0, "componentType": 5126, "count": 1, "type": "VEC5"}, id="no such type"
        ),
    ],
)
def test_every_accessor_must_lie_inside_its_buffer_view_even_one_nothing_draws(
    accessor: dict[str, Any],
) -> None:
    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=_add_accessor(accessor)))


def test_an_accessor_inside_its_view_that_nothing_draws_is_accepted() -> None:
    accessor = {"bufferView": 0, "componentType": 5126, "count": 24, "type": "SCALAR"}
    assert len(read_glb(build_glb(tweak=_add_accessor(accessor))).triangles) == 12


def test_the_stride_of_a_view_bounds_its_accessors() -> None:
    def strided(document: dict[str, Any]) -> None:  # 8 positions, 12 bytes apart, read 24 apart
        document["bufferViews"][0]["byteStride"] = 24
        document["accessors"].append(
            {"bufferView": 0, "componentType": 5126, "count": 5, "type": "VEC3"}
        )

    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=strided))


@pytest.mark.parametrize("where", ["attributes", "targets"])
def test_attributes_of_a_primitive_must_have_the_same_count(where: str) -> None:
    def mismatched(document: dict[str, Any]) -> None:
        document["accessors"].append(
            {"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"}
        )
        primitive = document["meshes"][0]["primitives"][0]
        if where == "attributes":
            primitive["attributes"]["NORMAL"] = 2
        else:
            primitive["targets"] = [{"POSITION": 2}]

    with pytest.raises(UnreadableModelError, match="count"):
        read_glb(build_glb(tweak=mismatched))


def test_a_mesh_no_scene_draws_still_counts_toward_the_vertex_limit() -> None:
    def hidden(document: dict[str, Any]) -> None:
        document["accessors"].append(
            {"bufferView": 0, "componentType": 5126, "count": MODEL_MAX_VERTICES, "type": "VEC3"}
        )
        document["meshes"].append({"primitives": [{"attributes": {"POSITION": 2}}]})

    with pytest.raises(ModelTooLargeError, match="vertices"):
        read_glb(build_glb(tweak=hidden))


def test_indices_of_every_mesh_count_toward_the_triangle_limit() -> None:
    def hidden(document: dict[str, Any]) -> None:
        document["accessors"].append(
            {
                "bufferView": 1,
                "componentType": 5125,
                "count": 3 * MODEL_MAX_TRIANGLES,
                "type": "SCALAR",
            }
        )
        document["meshes"].append({"primitives": [{"attributes": {"POSITION": 0}, "indices": 2}]})

    with pytest.raises(ModelTooLargeError, match="indices"):
        read_glb(build_glb(tweak=hidden))


def test_all_accessor_elements_together_are_capped() -> None:
    count = MODEL_MAX_ACCESSOR_ELEMENTS + 1
    accessor = {"bufferView": 0, "componentType": 5126, "count": count, "type": "SCALAR"}

    with pytest.raises(ModelTooLargeError, match="accessor elements"):
        read_glb(build_glb(tweak=_add_accessor(accessor)))


# KILN-36: the strict-tree rule covers every scene and every node, not only the default scene.
# The first three cases are the KILN-9 reviewer's files (glb_builder mirrors dag.mjs).


def _dag_in_no_scene(document: dict[str, Any]) -> None:
    add_doubling_chain(document)  # nodes no scene lists are still handed to the viewer


def _cycle_in_no_scene(document: dict[str, Any]) -> None:
    document["nodes"] += [{"children": [2]}, {"children": [1]}]


def _child_shared_across_scenes(document: dict[str, Any]) -> None:
    document["nodes"] += [{"children": [0]}]  # node 0 is a root of scene 0 and a child of 1
    document["scenes"].append({"nodes": [1]})


def _root_listed_twice(document: dict[str, Any]) -> None:
    document["scenes"].append({"nodes": [0, 0]})


@pytest.mark.parametrize(
    "tweak",
    [
        dag_in_a_second_scene,
        dag_in_the_default_scene,
        cycle_in_a_second_scene,
        _dag_in_no_scene,
        _cycle_in_no_scene,
        _child_shared_across_scenes,
        _root_listed_twice,
    ],
)
def test_a_node_reached_twice_anywhere_in_the_file_is_refused(tweak: Any) -> None:
    with pytest.raises(UnreadableModelError, match="reached twice"):
        read_glb(build_glb(tweak=tweak))


def test_a_too_deep_chain_in_a_second_scene_is_refused() -> None:
    def deep(document: dict[str, Any]) -> None:
        document["nodes"] += [{"children": [i + 2]} for i in range(100)] + [{"mesh": 0}]
        document["scenes"].append({"nodes": [1]})

    with pytest.raises(UnreadableModelError, match="too deep"):
        read_glb(build_glb(tweak=deep))


@pytest.mark.parametrize(
    "scene",
    [{"nodes": [99]}, {"nodes": "0"}, "scene", {"nodes": [True]}],
)
def test_a_broken_second_scene_is_refused(scene: object) -> None:
    def broken(document: dict[str, Any]) -> None:
        document["scenes"].append(scene)

    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=broken))


def test_well_formed_trees_in_several_scenes_and_a_node_in_two_scenes_are_accepted() -> None:
    def scenes(document: dict[str, Any]) -> None:
        document["nodes"] += [{"children": [2], "translation": [5, 0, 0]}, {"mesh": 0}, {}]
        document["scenes"] += [{"nodes": [1, 3]}, {"nodes": [0]}]  # node 0 in two scenes

    assert read_glb(build_glb(tweak=scenes)).triangles.shape == (12, 3, 3)


def test_a_wide_node_graph_is_checked_in_linear_time() -> None:
    def wide(document: dict[str, Any]) -> None:  # one long chain plus many leaves
        count = MODEL_MAX_OBJECTS - 1
        document["nodes"] = [{"children": [1]}] + [{"children": [i + 2]} for i in range(60)]
        document["nodes"] += [{} for _ in range(count - len(document["nodes"]))]
        document["nodes"].append({"mesh": 0})
        document["nodes"][60]["children"] = [count]
        document["scenes"] = [{"nodes": [0]}, {"nodes": list(range(62, count))}]

    started = time.monotonic()
    assert read_glb(build_glb(tweak=wide)).triangles.shape == (12, 3, 3)
    assert time.monotonic() - started < 2


# KILN-36 review round 1: three.js resolves every node's mesh, skin and camera and every skin's
# joints and skeleton, drawn or not, so each reference must be in range wherever the node is.
_BAD_INDICES = [99, -1, True, 1.0, "0"]


def _on_node_in_a_second_scene(field: str, value: object) -> Any:
    def tweak(document: dict[str, Any]) -> None:
        document["nodes"].append({field: value})
        document["scenes"].append({"nodes": [len(document["nodes"]) - 1]})

    return tweak


def _on_node_in_no_scene(field: str, value: object) -> Any:
    def tweak(document: dict[str, Any]) -> None:
        document["nodes"].append({field: value})

    return tweak


def _with_a_skin(skin: dict[str, Any]) -> Any:
    def tweak(document: dict[str, Any]) -> None:
        document["nodes"].append({})  # a node in no scene, joint of the skin
        document["skins"] = [skin]

    return tweak


@pytest.mark.parametrize("value", _BAD_INDICES)
@pytest.mark.parametrize("field", ["mesh", "skin", "camera"])
@pytest.mark.parametrize(
    "where", [_on_node_in_a_second_scene, _on_node_in_no_scene], ids=["second-scene", "no-scene"]
)
def test_a_node_reference_out_of_range_anywhere_is_refused(
    where: Any, field: str, value: object
) -> None:
    with pytest.raises(UnreadableModelError, match=f"bad {field} index"):
        read_glb(build_glb(tweak=where(field, value)))


@pytest.mark.parametrize("value", _BAD_INDICES)
@pytest.mark.parametrize("field", ["joints", "skeleton"])
def test_a_skin_naming_a_node_out_of_range_is_refused(field: str, value: object) -> None:
    skin: dict[str, Any] = {"joints": [1]}
    skin[field] = [value] if field == "joints" else value

    with pytest.raises(UnreadableModelError, match=r"bad (joint|skeleton) index"):
        read_glb(build_glb(tweak=_with_a_skin(skin)))


@pytest.mark.parametrize(
    "skins", [{"joints": [0]}, [{"joints": 0}], [{"joints": []}], ["skin"]], ids=str
)
def test_a_malformed_skin_is_refused(skins: object) -> None:
    def tweak(document: dict[str, Any]) -> None:
        document["skins"] = skins

    with pytest.raises(UnreadableModelError):
        read_glb(build_glb(tweak=tweak))


def test_valid_skins_cameras_and_meshes_on_nodes_no_scene_draws_are_accepted() -> None:
    def tweak(document: dict[str, Any]) -> None:
        document["nodes"] += [{"children": [2], "skin": 0, "mesh": 0}, {"camera": 0}]
        document["skins"] = [{"joints": [1, 2], "skeleton": 1}]
        document["cameras"] = [{"type": "perspective", "perspective": {"yfov": 1, "znear": 0.1}}]

    assert read_glb(build_glb(tweak=tweak)).triangles.shape == (12, 3, 3)
