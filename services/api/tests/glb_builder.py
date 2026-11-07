"""Builds small glTF 2.0 binaries for tests; `tweak` edits the JSON to make broken variants."""

import json
import struct
from collections.abc import Callable
from typing import Any

CUBE_POSITIONS = [
    (-1.0, -1.0, -1.0), (1.0, -1.0, -1.0), (1.0, 1.0, -1.0), (-1.0, 1.0, -1.0),
    (-1.0, -1.0, 1.0), (1.0, -1.0, 1.0), (1.0, 1.0, 1.0), (-1.0, 1.0, 1.0),
]  # fmt: skip
CUBE_INDICES = [
    0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
    2, 3, 7, 2, 7, 6, 1, 2, 6, 1, 6, 5, 0, 4, 7, 0, 7, 3,
]  # fmt: skip
_INDEX_FORMATS = {5121: "B", 5123: "H", 5125: "I"}


def _pad(data: bytes, filler: bytes) -> bytes:
    return data + filler * (-len(data) % 4)


def assemble(document: dict[str, Any] | bytes, binary: bytes = b"") -> bytes:
    """A GLB file from a JSON document (or raw JSON bytes) and a binary chunk."""
    raw = document if isinstance(document, bytes) else json.dumps(document).encode()
    json_chunk = _pad(raw, b" ")
    chunks = struct.pack("<II", len(json_chunk), 0x4E4F534A) + json_chunk
    if binary:
        bin_chunk = _pad(binary, b"\x00")
        chunks += struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
    return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks


def build_glb(
    positions: list[tuple[float, float, float]] = CUBE_POSITIONS,
    indices: list[int] | None = CUBE_INDICES,
    *,
    index_type: int = 5125,
    tweak: Callable[[dict[str, Any]], None] | None = None,
    binary_padding: int = 0,
) -> bytes:
    """One mesh in one node of one scene; `tweak` may rewrite the JSON before assembly."""
    position_bytes = b"".join(struct.pack("<3f", *p) for p in positions)
    binary = _pad(position_bytes, b"\x00")
    views: list[dict[str, Any]] = [
        {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes)}
    ]
    accessors: list[dict[str, Any]] = [
        {"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3"}
    ]
    primitive: dict[str, Any] = {"attributes": {"POSITION": 0}}
    if indices is not None:
        index_bytes = struct.pack(f"<{len(indices)}{_INDEX_FORMATS[index_type]}", *indices)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(index_bytes)})
        accessors.append(
            {"bufferView": 1, "componentType": index_type, "count": len(indices), "type": "SCALAR"}
        )
        binary = _pad(binary + index_bytes, b"\x00")
        primitive["indices"] = 1
    document: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": accessors,
        "meshes": [{"primitives": [primitive]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    if binary_padding > len(binary):  # room for tweaks that lengthen the first view
        binary += b"\x00" * (binary_padding - len(binary))
        document["buffers"][0]["byteLength"] = len(binary)
    if tweak is not None:
        tweak(document)
    return assemble(document, binary)


# KILN-36: the KILN-9 reviewer's crafted files (dag.mjs), as tweaks of `build_glb`'s cube.
DOUBLING_CHAIN_LENGTH = 24


def add_doubling_chain(document: dict[str, Any]) -> int:
    """Append nodes where each lists the next twice (a DAG) and the last holds the mesh.

    Returns the chain's first node; walked naively it has 2**23 paths to the mesh.
    """
    first = len(document["nodes"])
    document["nodes"] += [
        {"children": [first + i + 1, first + i + 1]}
        if i < DOUBLING_CHAIN_LENGTH - 1
        else {"mesh": 0}
        for i in range(DOUBLING_CHAIN_LENGTH)
    ]
    return first


def dag_in_a_second_scene(document: dict[str, Any]) -> None:
    """dag.mjs `scene1`: the default scene is a valid cube; a second scene holds the DAG."""
    document["scenes"].append({"nodes": [add_doubling_chain(document)]})


def dag_in_the_default_scene(document: dict[str, Any]) -> None:
    """dag.mjs `scene0`: the DAG is a second root of the default scene."""
    document["scenes"][0]["nodes"].append(add_doubling_chain(document))


def cycle_in_a_second_scene(document: dict[str, Any]) -> None:
    """dag.mjs `cycle`: a node that is its own child, the root of a second scene."""
    document["nodes"].append({"children": [len(document["nodes"])]})
    document["scenes"].append({"nodes": [len(document["nodes"]) - 1]})
