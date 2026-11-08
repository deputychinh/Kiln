"""Named constants for the API."""

from kiln_api.enums import AssetKind, VersionStatus

API_PREFIX = "/api/v1"
API_TITLE = "Kiln API"
API_VERSION = "0.1.0"
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
    # A ready file the worker's current rules refuse is failed by `make recheck-models` (KILN-36).
    VersionStatus.READY: frozenset({VersionStatus.FAILED}),
}
PAGE_LIMIT_MIN = 1
PAGE_LIMIT_MAX = 100
PAGE_LIMIT_DEFAULT = 24
OBJECT_KEY_PREFIX = "assets"
THUMBNAIL_KEY_PREFIX = "thumbs"
DOWNLOAD_URL_TTL_SECONDS = 15 * 60
# Previews are signed at the start of a window, so a URL stays the same (and the browser cache
# hits) for the whole window; each URL then lives TTL + window, at least TTL after it is handed
# out (KILN-27).
DOWNLOAD_URL_WINDOW_SECONDS = 10 * 60
# S3 accepts presigned URLs valid for 1 second up to 7 days.
PRESIGN_MIN_SECONDS = 1
PRESIGN_MAX_SECONDS = 7 * 24 * 60 * 60
DOWNLOAD_URL_LIFETIME_SECONDS = DOWNLOAD_URL_TTL_SECONDS + DOWNLOAD_URL_WINDOW_SECONDS
# A version's thumbnail never changes; private keeps it out of shared caches.
DOWNLOAD_CACHE_CONTROL = f"private, max-age={DOWNLOAD_URL_LIFETIME_SECONDS}, immutable"
JOB_LEASE_SECONDS = 5 * 60
# A running job extends its lease every third of it (KILN-24), and stops after this long, so a
# hung job's lease expires and it is retried or buried like a crashed one.
JOB_HEARTBEAT_SECONDS = JOB_LEASE_SECONDS / 3
JOB_MAX_RUNTIME_SECONDS = 30 * 60
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
# Circuit breaker and bulkhead around storage calls (KILN-23).
STORAGE_BREAKER_FAILURES = 5
STORAGE_BREAKER_COOLDOWN_SECONDS = 30.0
STORAGE_MAX_CONCURRENT = 16
# Sync endpoints share AnyIO's 40-thread pool; keep 8 threads free for requests not on storage.
STORAGE_MAX_CONCURRENT_LIMIT = 32
STORAGE_BULKHEAD_WAIT_SECONDS = 0.5
DB_CONNECT_TIMEOUT_SECONDS = 5
DB_LOCK_TIMEOUT_MS = 5_000
DB_STATEMENT_TIMEOUT_MS = 15_000
# Migrations: a DDL statement waits at most this long for a lock (then fails, so it never queues
# writers behind it), and a statement such as VALIDATE CONSTRAINT may scan this long.
MIGRATION_LOCK_TIMEOUT_MS = 5_000
MIGRATION_STATEMENT_TIMEOUT_MS = 10 * 60_000
# A dead TCP link (no FIN, no RST) must not block a session forever: unacknowledged data fails the
# socket after 30 s and an idle one is probed every 5 s after 10 s, three times (KILN-28 review).
DB_TCP_USER_TIMEOUT_MS = 30_000
DB_KEEPALIVES_IDLE_SECONDS = 10
DB_KEEPALIVES_INTERVAL_SECONDS = 5
DB_KEEPALIVES_COUNT = 3
# How long a finished job waits for an in-flight extension before moving on: longer than any
# statement may run, so the outcome write never queues behind an extension's row lock.
JOB_HEARTBEAT_JOIN_SECONDS = DB_STATEMENT_TIMEOUT_MS / 1000 + 5
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
# The staging sweep reads at most this many old keys per run (skipped ones included), so keys it
# must keep (still waiting, or not written by Kiln) cannot make a run unbounded.
MAINTENANCE_SCAN_LIMIT = 10 * MAINTENANCE_BATCH_SIZE
# Versions are looked up this many keys at a time (one query per chunk, not per key).
MAINTENANCE_LOOKUP_CHUNK = 100
# Expired idempotency keys are purged in up to this many batches per run (5,000 keys).
MAINTENANCE_PURGE_BATCHES = 10
MAINTENANCE_INTERVAL_SECONDS = 60 * 60
MAINTENANCE_TASK = "cleanup"
LOCK_NOT_AVAILABLE_SQLSTATE = "55P03"
# Edge limits on JSON fields; generous so the domain reports the precise rule that failed.
MAX_NAME_FIELD_LENGTH = 1_000
MAX_FILE_NAME_FIELD_LENGTH = 2_000
MAX_CONTENT_TYPE_FIELD_LENGTH = 255
# Bound for reading one asset's history; review UIs page beyond this (KILN-8).
MAX_VERSIONS_PER_READ = 500

# --- identity (KILN-12) ------------------------------------------------------------------------
# Argon2id with the OWASP Password Storage Cheat Sheet's second configuration (19 MiB, t=2, p=1);
# about 20 ms per hash on a laptop. Changing these re-hashes each password at its next sign-in.
ARGON2_MEMORY_KIB = 19_456
ARGON2_TIME_COST = 2
ARGON2_PARALLELISM = 1
PASSWORD_MIN_LENGTH = 12  # ASVS 5.0 V6.2.1 (at least 8; 15 recommended without MFA in NIST 63B)
PASSWORD_MAX_LENGTH = 128  # ASVS V6.2.9: at least 64 must be allowed; bounds the hash work
EMAIL_MAX_LENGTH = 254
DISPLAY_NAME_MAX_LENGTH = 80
# Sessions: opaque 256-bit ids stored only as SHA-256; OWASP Session Management Cheat Sheet:
# 15-30 min idle for low-risk apps, an absolute bound of a working day (4-8 h).
SESSION_ID_BYTES = 32
SESSION_IDLE_MINUTES = 30
SESSION_ABSOLUTE_HOURS = 8
# A session's last-seen time is written at most this often (not on every request).
SESSION_TOUCH_SECONDS = 60
SESSION_COOKIE_LOCAL = "kiln_session"
# The `__Host-` prefix needs Secure, Path=/ and no Domain, so it is used only over HTTPS.
SESSION_COOKIE_SECURE = "__Host-kiln_session"
# Cookie-authenticated writes must carry this header (a cross-site page cannot add it without a
# CORS preflight the API refuses) and an allowed Origin (OWASP CSRF Prevention Cheat Sheet).
CSRF_HEADER = "X-Kiln-Csrf"
CSRF_HEADER_VALUE = "1"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Personal access tokens: `kiln_pat_` + 43 URL-safe characters (256 random bits), SHA-256 stored.
ACCESS_TOKEN_PREFIX = "kiln_pat_"  # noqa: S105 - a public marker, not a secret
ACCESS_TOKEN_BYTES = 32
ACCESS_TOKEN_SHOWN_PREFIX_LENGTH = len(ACCESS_TOKEN_PREFIX) + 6
ACCESS_TOKEN_NAME_MAX_LENGTH = 80
ACCESS_TOKEN_EXPIRY_DAYS = (7, 30, 90, 365)
ACCESS_TOKEN_MAX_PER_USER = 50
ACCESS_TOKEN_TOUCH_SECONDS = 60
# Sign-in throttling: failures counted per account (normalised email, existing or not) and per
# client IP in a sliding window; past either limit the API answers 429 without checking.
SIGN_IN_WINDOW_MINUTES = 15
SIGN_IN_MAX_FAILURES_PER_ACCOUNT = 10
SIGN_IN_MAX_FAILURES_PER_IP = 50
AUTH_REALM = "kiln"

# --- comments and region annotations (KILN-10) --------------------------------------------------
COMMENT_BODY_MAX_LENGTH = 2_000
# Edge limit on the JSON field; generous so the domain reports the precise rule.
MAX_COMMENT_BODY_FIELD_LENGTH = 10_000
COMMENT_PAGE_LIMIT_MIN = 1
COMMENT_PAGE_LIMIT_MAX = 100
COMMENT_PAGE_LIMIT_DEFAULT = 50
# Regions are normalised to the image: 0 to 1 on each axis, origin top left (Frame.io's model).
REGION_MIN = 0.0
REGION_MAX = 1.0
# A rectangle is at least 1 % of the image on each side (5 px on a 512 px preview), so it is
# always drawn; the web app's smallest drag is 2 %.
REGION_MIN_SIZE = 0.01

# --- review states and history (KILN-11) ----------------------------------------------------------
REVIEW_NOTE_MAX_LENGTH = 1_000
REVIEW_PAGE_LIMIT_MIN = 1
REVIEW_PAGE_LIMIT_MAX = 100
REVIEW_PAGE_LIMIT_DEFAULT = 50
