from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from kiln_api.constants import ALLOWED_TRANSITIONS, MAX_UPLOAD_BYTES
from kiln_api.domain.assets import UploadSpec, new_asset, new_version, transition
from kiln_api.enums import AssetKind, VersionStatus
from kiln_api.errors import (
    AssetKindMismatchError,
    InvalidAssetNameError,
    InvalidFileNameError,
    InvalidFileSizeError,
    InvalidStatusTransitionError,
    UnsupportedMediaTypeError,
)

NOW = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
PNG = UploadSpec(file_name="T_Rock_01_BaseColor.png", content_type="image/png", size_bytes=2048)
GLB = UploadSpec(file_name="SM_Rock_01.glb", content_type="model/gltf-binary", size_bytes=4096)


def _ids() -> Callable[[], UUID]:
    counter = iter(range(1, 1000))
    return lambda: UUID(int=next(counter))


def test_a_new_asset_starts_with_version_one_pending_upload() -> None:
    asset, version = new_asset("  Rock  ", PNG, now=NOW, new_id=_ids())

    assert asset.name == "Rock"
    assert asset.kind is AssetKind.IMAGE
    assert asset.created_at == asset.updated_at == NOW
    assert version.asset_id == asset.id
    assert version.number == 1
    assert version.status is VersionStatus.PENDING_UPLOAD
    assert version.file_name == "T_Rock_01_BaseColor.png"
    assert version.size_bytes == 2048


def test_the_object_key_is_built_by_the_server_and_never_contains_the_file_name() -> None:
    _, version = new_asset("Rock", PNG, now=NOW, new_id=_ids())

    assert version.object_key.startswith(f"assets/{version.asset_id}/v1/")
    assert "Rock" not in version.object_key
    assert version.object_key.endswith(".png")


def test_a_glb_upload_makes_a_model_asset() -> None:
    asset, version = new_asset("Rock mesh", GLB, now=NOW, new_id=_ids())

    assert asset.kind is AssetKind.MODEL
    assert version.object_key.endswith(".glb")


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "x" * 121,
        "bad\nname",
        "tab\tname",
        "nul\x00",
        "\u202egnp.exe",
        "a\u200bb",
        "a\u2028b",
    ],
)
def test_invalid_asset_names_are_rejected(name: str) -> None:
    with pytest.raises(InvalidAssetNameError):
        new_asset(name, PNG, now=NOW, new_id=_ids())


def test_a_name_of_exactly_120_characters_is_accepted() -> None:
    asset, _ = new_asset("x" * 120, PNG, now=NOW, new_id=_ids())

    assert len(asset.name) == 120


@pytest.mark.parametrize("content_type", ["image/gif", "application/zip", "text/html", ""])
def test_unsupported_media_types_are_rejected(content_type: str) -> None:
    spec = UploadSpec(file_name="a.bin", content_type=content_type, size_bytes=10)

    with pytest.raises(UnsupportedMediaTypeError):
        new_asset("Rock", spec, now=NOW, new_id=_ids())


def test_media_types_are_matched_case_insensitively_with_parameters_ignored() -> None:
    spec = UploadSpec(file_name="a.jpg", content_type="IMAGE/JPEG; charset=binary", size_bytes=1)

    asset, version = new_asset("Rock", spec, now=NOW, new_id=_ids())

    assert asset.kind is AssetKind.IMAGE
    assert version.content_type == "image/jpeg"


@pytest.mark.parametrize("size", [0, -1, MAX_UPLOAD_BYTES + 1])
def test_sizes_outside_one_byte_to_500_mb_are_rejected(size: int) -> None:
    spec = UploadSpec(file_name="a.png", content_type="image/png", size_bytes=size)

    with pytest.raises(InvalidFileSizeError):
        new_asset("Rock", spec, now=NOW, new_id=_ids())


@pytest.mark.parametrize("size", [1, MAX_UPLOAD_BYTES])
def test_the_size_boundaries_are_accepted(size: int) -> None:
    spec = UploadSpec(file_name="a.png", content_type="image/png", size_bytes=size)

    _, version = new_asset("Rock", spec, now=NOW, new_id=_ids())

    assert version.size_bytes == size


@pytest.mark.parametrize(
    ("file_name", "stored"),
    [
        ("../../etc/passwd.png", "passwd.png"),
        ("C:\\tex\\rock.png", "rock.png"),
        (" a.png ", "a.png"),
    ],
)
def test_directories_are_stripped_from_file_names(file_name: str, stored: str) -> None:
    spec = UploadSpec(file_name=file_name, content_type="image/png", size_bytes=1)

    _, version = new_asset("Rock", spec, now=NOW, new_id=_ids())

    assert version.file_name == stored


@pytest.mark.parametrize(
    "file_name",
    ["", "dir/", "  ", "x" * 256, "a\nb.png", ".", "..", "foo/..", "\u202egnp.exe", "a\u200b.png"],
)
def test_blank_long_or_control_character_file_names_are_rejected(file_name: str) -> None:
    spec = UploadSpec(file_name=file_name, content_type="image/png", size_bytes=1)

    with pytest.raises(InvalidFileNameError):
        new_asset("Rock", spec, now=NOW, new_id=_ids())


def test_a_new_version_takes_the_given_number_and_starts_pending() -> None:
    asset, _ = new_asset("Rock", PNG, now=NOW, new_id=_ids())
    later = NOW + timedelta(hours=1)

    version = new_version(asset, 2, PNG, now=later, new_id=_ids())

    assert version.number == 2
    assert version.status is VersionStatus.PENDING_UPLOAD
    assert version.object_key.startswith(f"assets/{asset.id}/v2/")
    assert version.created_at == later


def test_a_version_of_another_kind_is_rejected() -> None:
    asset, _ = new_asset("Rock", PNG, now=NOW, new_id=_ids())

    with pytest.raises(AssetKindMismatchError):
        new_version(asset, 2, GLB, now=NOW, new_id=_ids())


@pytest.mark.parametrize(
    "path",
    [
        [VersionStatus.PROCESSING, VersionStatus.READY],
        [VersionStatus.PROCESSING, VersionStatus.FAILED],
        [
            VersionStatus.PROCESSING,
            VersionStatus.FAILED,
            VersionStatus.PROCESSING,
            VersionStatus.READY,
        ],
    ],
)
def test_allowed_status_paths(path: list[VersionStatus]) -> None:
    _, version = new_asset("Rock", PNG, now=NOW, new_id=_ids())
    later = NOW + timedelta(minutes=5)

    for status in path:
        version = transition(version, status, now=later)

    assert version.status is path[-1]
    assert version.updated_at == later


_PATH_TO = {
    VersionStatus.PENDING_UPLOAD: [],
    VersionStatus.PROCESSING: [VersionStatus.PROCESSING],
    VersionStatus.READY: [VersionStatus.PROCESSING, VersionStatus.READY],
    VersionStatus.FAILED: [VersionStatus.PROCESSING, VersionStatus.FAILED],
}
_FORBIDDEN = [
    (start, target)
    for start in VersionStatus
    for target in VersionStatus
    if target not in ALLOWED_TRANSITIONS[start]
]


def test_the_transition_table_covers_all_sixteen_pairs() -> None:
    allowed = sum(len(targets) for targets in ALLOWED_TRANSITIONS.values())

    assert allowed + len(_FORBIDDEN) == len(VersionStatus) ** 2 == 16


@pytest.mark.parametrize(("start", "target"), _FORBIDDEN)
def test_forbidden_status_transitions_raise(start: VersionStatus, target: VersionStatus) -> None:
    _, version = new_asset("Rock", PNG, now=NOW, new_id=_ids())
    for status in _PATH_TO[start]:
        version = transition(version, status, now=NOW)

    with pytest.raises(InvalidStatusTransitionError):
        transition(version, target, now=NOW)


def test_timestamps_without_a_timezone_are_a_programming_error() -> None:
    naive = datetime(2026, 11, 3, 9, 0)  # noqa: DTZ001 - the point of the test

    with pytest.raises(ValueError, match="timezone"):
        new_asset("Rock", PNG, now=naive, new_id=_ids())
    _, version = new_asset("Rock", PNG, now=NOW, new_id=_ids())
    with pytest.raises(ValueError, match="timezone"):
        transition(version, VersionStatus.PROCESSING, now=naive)
