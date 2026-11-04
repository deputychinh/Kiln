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
# The one table of supported uploads: media type -> (kind, stored file extension).
MEDIA_TYPES: dict[str, tuple[AssetKind, str]] = {
    "image/png": (AssetKind.IMAGE, "png"),
    "image/jpeg": (AssetKind.IMAGE, "jpg"),
    "image/webp": (AssetKind.IMAGE, "webp"),
    "model/gltf-binary": (AssetKind.MODEL, "glb"),
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
UPLOAD_URL_TTL_SECONDS = 15 * 60
STORAGE_TIMEOUT_SECONDS = 10
STORAGE_MAX_ATTEMPTS = 2
DB_LOCK_TIMEOUT_MS = 5_000
DB_STATEMENT_TIMEOUT_MS = 15_000
# Edge limits on JSON fields; generous so the domain reports the precise rule that failed.
MAX_NAME_FIELD_LENGTH = 1_000
MAX_FILE_NAME_FIELD_LENGTH = 2_000
MAX_CONTENT_TYPE_FIELD_LENGTH = 255
# Bound for reading one asset's history; review UIs page beyond this (KILN-8).
MAX_VERSIONS_PER_READ = 500
