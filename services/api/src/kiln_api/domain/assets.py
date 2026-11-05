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
    MEDIA_TYPES,
    OBJECT_KEY_PREFIX,
    THUMBNAIL_KEY_PREFIX,
    UPLOAD_KEY_PREFIX,
)
from kiln_api.enums import AssetKind, FailureReason, VersionStatus
from kiln_api.errors import (
    AssetKindMismatchError,
    InvalidAssetNameError,
    InvalidFileNameError,
    InvalidFileSizeError,
    InvalidStatusTransitionError,
    UnsupportedMediaTypeError,
)

# Invisible or text-reordering characters (Trojan Source, CVE-2021-42574; tag characters used to
# smuggle text into AI prompts). All format characters (Cf) are rejected except ZWNJ/ZWJ, which
# Persian, Indic scripts and emoji sequences need; lone surrogates (Cs) cannot be stored at all.
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
_ALLOWED_FORMAT_CHARACTERS = frozenset("\u200c\u200d")
# Not Cf but render as nothing: combining grapheme joiner, Hangul and Braille fillers.
_INVISIBLE_CHARACTERS = frozenset("\u034f\u115f\u1160\u17b4\u17b5\u2800\u3164\uffa0")
# A name must show something: at least one letter, number, punctuation or symbol.
_VISIBLE_CATEGORY_CLASSES = frozenset("LNPS")

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
    cover_version_id: UUID | None = None  # newest ready version, shown in the gallery


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
    etag: str | None = None  # of the final object, recorded at completion (ADR 0005)
    failure_reason: FailureReason | None = None


def _is_unreadable(text: str) -> bool:
    has_visible = any(
        unicodedata.category(char)[0] in _VISIBLE_CATEGORY_CLASSES
        and char not in _INVISIBLE_CHARACTERS
        for char in text
    )
    return not has_visible or _has_hidden_characters(text)


def _has_hidden_characters(text: str) -> bool:
    return any(
        char in _INVISIBLE_CHARACTERS
        or (
            unicodedata.category(char) in _FORBIDDEN_CATEGORIES
            and char not in _ALLOWED_FORMAT_CHARACTERS
        )
        for char in text
    )


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None:
        msg = "Domain timestamps must carry a timezone."
        raise ValueError(msg)


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or len(cleaned) > ASSET_NAME_MAX_LENGTH or _is_unreadable(cleaned):
        raise InvalidAssetNameError
    return cleaned


def _clean_file_name(file_name: str) -> str:
    base = re.split(r"[\\/]", file_name)[-1].strip()
    if not base or set(base) == {"."} or len(base) > FILE_NAME_MAX_LENGTH or _is_unreadable(base):
        raise InvalidFileNameError
    return base


def _media_type(content_type: str) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in MEDIA_TYPES:
        raise UnsupportedMediaTypeError
    return media_type


def _build_version(
    asset: Asset, number: int, spec: UploadSpec, *, now: datetime, new_id: IdFactory
) -> AssetVersion:
    _require_aware(now)
    media_type = _media_type(spec.content_type)
    kind, extension = MEDIA_TYPES[media_type]
    if kind is not asset.kind:
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
        object_key=f"{OBJECT_KEY_PREFIX}/{asset.id}/v{number}/{version_id}.{extension}",
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
        kind=MEDIA_TYPES[_media_type(spec.content_type)][0],
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


def transition(
    version: AssetVersion,
    status: VersionStatus,
    *,
    now: datetime,
    failure_reason: FailureReason | None = None,
) -> AssetVersion:
    """Move a version to `status` if the life cycle allows it.

    A `failed` version must carry a `failure_reason`; any other status clears it.

    Raises:
        InvalidStatusTransitionError: The move is not in `ALLOWED_TRANSITIONS`.
        ValueError: A reason is missing for `failed` or given for another status.
    """
    _require_aware(now)
    if status not in ALLOWED_TRANSITIONS[version.status]:
        raise InvalidStatusTransitionError(version.status, status)
    if (status is VersionStatus.FAILED) != (failure_reason is not None):
        msg = "A failure reason is required for failed versions and only for them."
        raise ValueError(msg)
    return replace(version, status=status, updated_at=now, failure_reason=failure_reason)


def upload_key(version: AssetVersion) -> str:
    """The staging key a signed form may write; never the final `object_key`."""
    return f"{UPLOAD_KEY_PREFIX}/{version.asset_id}/{version.id}"


def thumbnail_key(version: AssetVersion) -> str:
    """Where the worker writes the preview of `version`."""
    return thumbnail_key_for(version.asset_id, version.id)


def thumbnail_key_for(asset_id: UUID, version_id: UUID) -> str:
    """The preview key from ids alone (used for an asset's cover)."""
    return f"{THUMBNAIL_KEY_PREFIX}/{asset_id}/{version_id}.webp"
