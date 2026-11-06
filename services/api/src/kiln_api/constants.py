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
    # An upload never completed is expired by maintenance (KILN-22).
    VersionStatus.PENDING_UPLOAD: frozenset({VersionStatus.PROCESSING, VersionStatus.FAILED}),
    VersionStatus.PROCESSING: frozenset({VersionStatus.READY, VersionStatus.FAILED}),
    VersionStatus.FAILED: frozenset({VersionStatus.PROCESSING}),
    VersionStatus.READY: frozenset(),
}
PAGE_LIMIT_MIN = 1
PAGE_LIMIT_MAX = 100
PAGE_LIMIT_DEFAULT = 24
OBJECT_KEY_PREFIX = "assets"
THUMBNAIL_KEY_PREFIX = "thumbs"
DOWNLOAD_URL_TTL_SECONDS = 15 * 60
JOB_LEASE_SECONDS = 5 * 60
JOB_MAX_ATTEMPTS = 5
JOB_BACKOFF_BASE_SECONDS = 5
# Signed forms write only to a staging key; completion copies to the final key (immutable).
UPLOAD_KEY_PREFIX = "uploads"
UPLOAD_URL_TTL_SECONDS = 15 * 60
# Worst case per storage call: 2 attempts x (3 s connect + 10 s read) = 26 s.
STORAGE_CONNECT_TIMEOUT_SECONDS = 3
STORAGE_READ_TIMEOUT_SECONDS = 10
STORAGE_TOTAL_ATTEMPTS = 2
# Readiness must answer fast: one attempt, 1 s to connect and to read.
STORAGE_PROBE_TIMEOUT_SECONDS = 1
DB_LOCK_TIMEOUT_MS = 5_000
DB_STATEMENT_TIMEOUT_MS = 15_000
# SQLSTATEs for lock_timeout and statement_timeout: the database is busy, retry later.
DB_BUSY_SQLSTATES = frozenset({"55P03", "57014"})
RETRY_AFTER_SECONDS = 1
MAX_JSON_BODY_BYTES = 1024 * 1024
# Idempotency-Key (IETF draft-ietf-httpapi-idempotency-key-header-08): sf-string, 24 h window.
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENT_REPLAYED_HEADER = "Idempotent-Replayed"
IDEMPOTENCY_KEY_MAX_LENGTH = 255
IDEMPOTENCY_WINDOW_HOURS = 24
# Maintenance (KILN-22): a version still pending this long is abandoned, and staging objects this
# old whose version moved on are garbage. Each sweep handles at most a batch per run.
UPLOAD_ABANDONED_AFTER_HOURS = 24
MAINTENANCE_BATCH_SIZE = 500
MAINTENANCE_INTERVAL_SECONDS = 60 * 60
MAINTENANCE_TASK = "cleanup"
LOCK_NOT_AVAILABLE_SQLSTATE = "55P03"
# Edge limits on JSON fields; generous so the domain reports the precise rule that failed.
MAX_NAME_FIELD_LENGTH = 1_000
MAX_FILE_NAME_FIELD_LENGTH = 2_000
MAX_CONTENT_TYPE_FIELD_LENGTH = 255
# Bound for reading one asset's history; review UIs page beyond this (KILN-8).
MAX_VERSIONS_PER_READ = 500
