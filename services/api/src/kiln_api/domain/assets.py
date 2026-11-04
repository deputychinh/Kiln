"""Assets and their versions: creation rules and the version status machine."""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from kiln_api.constants import (
    ALLOWED_TRANSITIONS,
    ASSET_NAME_MAX_LENGTH,
    FILE_NAME_MAX_LENGTH,
    MAX_UPLOAD_BYTES,
    MEDIA_TYPE_KINDS,
    OBJECT_KEY_PREFIX,
)
from kiln_api.enums import AssetKind, VersionStatus
from kiln_api.errors import (
    AssetKindMismatchError,
    InvalidAssetNameError,
    InvalidFileNameError,
    InvalidFileSizeError,
    InvalidStatusTransitionError,
    UnsupportedMediaTypeError,
)

# Control, format (bidi overrides, zero-width) and line/paragraph separators can disguise a name.
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})
_DOT_NAMES = frozenset({".", ".."})
_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "model/gltf-binary": "glb",
}

type IdFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class UploadSpec:
    """What the client says it is about to upload."""

    file_name: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class Asset:
    """A named piece of work that collects versions."""

    id: UUID
    name: str
    kind: AssetKind
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AssetVersion:
    """One uploaded file of an asset, numbered from 1."""

    id: UUID
    asset_id: UUID
    number: int
    status: VersionStatus
    file_name: str
    content_type: str
    size_bytes: int
    object_key: str
    created_at: datetime
    updated_at: datetime


def _has_hidden_characters(text: str) -> bool:
    return any(unicodedata.category(char) in _FORBIDDEN_CATEGORIES for char in text)


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None:
        msg = "Domain timestamps must carry a timezone."
        raise ValueError(msg)


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or len(cleaned) > ASSET_NAME_MAX_LENGTH or _has_hidden_characters(cleaned):
        raise InvalidAssetNameError
    return cleaned


def _clean_file_name(file_name: str) -> str:
    base = re.split(r"[\\/]", file_name)[-1].strip()
    if (
        not base
        or base in _DOT_NAMES
        or len(base) > FILE_NAME_MAX_LENGTH
        or _has_hidden_characters(base)
    ):
        raise InvalidFileNameError
    return base


def _media_type(content_type: str) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in MEDIA_TYPE_KINDS:
        raise UnsupportedMediaTypeError
    return media_type


def _build_version(
    asset: Asset, number: int, spec: UploadSpec, *, now: datetime, new_id: IdFactory
) -> AssetVersion:
    _require_aware(now)
    media_type = _media_type(spec.content_type)
    if MEDIA_TYPE_KINDS[media_type] is not asset.kind:
        raise AssetKindMismatchError
    if not 1 <= spec.size_bytes <= MAX_UPLOAD_BYTES:
        raise InvalidFileSizeError
    version_id = new_id()
    return AssetVersion(
        id=version_id,
        asset_id=asset.id,
        number=number,
        status=VersionStatus.PENDING_UPLOAD,
        file_name=_clean_file_name(spec.file_name),
        content_type=media_type,
        size_bytes=spec.size_bytes,
        object_key=f"{OBJECT_KEY_PREFIX}/{asset.id}/v{number}/{version_id}.{_EXTENSIONS[media_type]}",
        created_at=now,
        updated_at=now,
    )


def new_asset(
    name: str, spec: UploadSpec, *, now: datetime, new_id: IdFactory
) -> tuple[Asset, AssetVersion]:
    """Create an asset and its first version, waiting for the upload.

    Raises:
        InvalidAssetNameError, InvalidFileNameError, InvalidFileSizeError,
        UnsupportedMediaTypeError: The input breaks a rule.
    """
    _require_aware(now)
    asset = Asset(
        id=new_id(),
        name=_clean_name(name),
        kind=MEDIA_TYPE_KINDS[_media_type(spec.content_type)],
        created_at=now,
        updated_at=now,
    )
    return asset, _build_version(asset, 1, spec, now=now, new_id=new_id)


def new_version(
    asset: Asset, number: int, spec: UploadSpec, *, now: datetime, new_id: IdFactory
) -> AssetVersion:
    """Create version `number` of `asset`; the repository chooses the number.

    Raises:
        AssetKindMismatchError: The file is of another kind than the asset.
    """
    return _build_version(asset, number, spec, now=now, new_id=new_id)


def transition(version: AssetVersion, status: VersionStatus, *, now: datetime) -> AssetVersion:
    """Move a version to `status` if the life cycle allows it.

    Raises:
        InvalidStatusTransitionError: The move is not in `ALLOWED_TRANSITIONS`.
    """
    _require_aware(now)
    if status not in ALLOWED_TRANSITIONS[version.status]:
        raise InvalidStatusTransitionError(version.status, status)
    return replace(version, status=status, updated_at=now)
