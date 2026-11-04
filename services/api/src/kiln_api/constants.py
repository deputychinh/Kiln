"""Named constants for the API."""

from kiln_api.enums import AssetKind, VersionStatus

API_PREFIX = "/api/v1"
API_TITLE = "Kiln API"
API_VERSION = "0.0.0"
PROBLEM_JSON = "application/problem+json"
REQUEST_ID_HEADER = "X-Request-Id"

ASSET_NAME_MAX_LENGTH = 120
FILE_NAME_MAX_LENGTH = 255
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MEDIA_TYPE_KINDS: dict[str, AssetKind] = {
    "image/png": AssetKind.IMAGE,
    "image/jpeg": AssetKind.IMAGE,
    "image/webp": AssetKind.IMAGE,
    "model/gltf-binary": AssetKind.MODEL,
}
ALLOWED_TRANSITIONS: dict[VersionStatus, frozenset[VersionStatus]] = {
    VersionStatus.PENDING_UPLOAD: frozenset({VersionStatus.PROCESSING}),
    VersionStatus.PROCESSING: frozenset({VersionStatus.READY, VersionStatus.FAILED}),
    VersionStatus.FAILED: frozenset({VersionStatus.PROCESSING}),
    VersionStatus.READY: frozenset(),
}
PAGE_LIMIT_MIN = 1
PAGE_LIMIT_MAX = 100
PAGE_LIMIT_DEFAULT = 24
OBJECT_KEY_PREFIX = "assets"
