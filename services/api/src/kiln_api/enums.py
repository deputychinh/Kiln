"""Enumerations shared across the API; the single source for codes and states."""

from enum import StrEnum


class Environment(StrEnum):
    """Where the process runs."""

    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class ErrorCode(StrEnum):
    """Stable error codes returned in the `code` field of problem details."""

    NOT_FOUND = "NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INTERNAL = "INTERNAL"
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
    ASSET_VERSION_NOT_FOUND = "ASSET_VERSION_NOT_FOUND"
    INVALID_ASSET_NAME = "INVALID_ASSET_NAME"
    INVALID_FILE_NAME = "INVALID_FILE_NAME"
    INVALID_FILE_SIZE = "INVALID_FILE_SIZE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    ASSET_KIND_MISMATCH = "ASSET_KIND_MISMATCH"
    INVALID_STATUS_TRANSITION = "INVALID_STATUS_TRANSITION"
    INVALID_CURSOR = "INVALID_CURSOR"
    UPLOAD_NOT_FOUND = "UPLOAD_NOT_FOUND"
    UPLOAD_MISMATCH = "UPLOAD_MISMATCH"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    DATABASE_BUSY = "DATABASE_BUSY"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    INVALID_IDEMPOTENCY_KEY = "INVALID_IDEMPOTENCY_KEY"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    IDEMPOTENCY_KEY_IN_USE = "IDEMPOTENCY_KEY_IN_USE"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    SIGN_IN_THROTTLED = "SIGN_IN_THROTTLED"
    CSRF_CHECK_FAILED = "CSRF_CHECK_FAILED"
    INSUFFICIENT_SCOPE = "INSUFFICIENT_SCOPE"
    SESSION_REQUIRED = "SESSION_REQUIRED"
    ACCESS_TOKEN_NOT_FOUND = "ACCESS_TOKEN_NOT_FOUND"  # noqa: S105 - an error code, not a secret
    ACCESS_TOKEN_LIMIT = "ACCESS_TOKEN_LIMIT"  # noqa: S105 - an error code, not a secret
    INVALID_EMAIL = "INVALID_EMAIL"
    INVALID_DISPLAY_NAME = "INVALID_DISPLAY_NAME"
    WEAK_PASSWORD = "WEAK_PASSWORD"  # noqa: S105 - an error code, not a secret
    EMAIL_TAKEN = "EMAIL_TAKEN"
    INVALID_TOKEN_NAME = "INVALID_TOKEN_NAME"  # noqa: S105 - an error code, not a secret
    COMMENT_THREAD_NOT_FOUND = "COMMENT_THREAD_NOT_FOUND"
    COMMENT_NOT_FOUND = "COMMENT_NOT_FOUND"
    INVALID_COMMENT_BODY = "INVALID_COMMENT_BODY"
    INVALID_REGION = "INVALID_REGION"
    REGION_NOT_SUPPORTED = "REGION_NOT_SUPPORTED"
    NOT_COMMENT_AUTHOR = "NOT_COMMENT_AUTHOR"
    COMMENT_DELETED = "COMMENT_DELETED"
    REVIEW_EVENT_NOT_FOUND = "REVIEW_EVENT_NOT_FOUND"
    INVALID_REVIEW_NOTE = "INVALID_REVIEW_NOTE"
    INVALID_REVIEW_TRANSITION = "INVALID_REVIEW_TRANSITION"
    REVIEW_STATE_CONFLICT = "REVIEW_STATE_CONFLICT"
    VERSION_NOT_READY = "VERSION_NOT_READY"


class HealthStatus(StrEnum):
    """Result of a health or readiness probe."""

    OK = "ok"


class AssetKind(StrEnum):
    """What an asset holds; decides how it is previewed."""

    IMAGE = "image"
    MODEL = "model"


class VersionStatus(StrEnum):
    """Life cycle of one uploaded version."""

    PENDING_UPLOAD = "pending_upload"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class PromotionResult(StrEnum):
    """Outcome of copying a staged upload to its final key."""

    PROMOTED = "promoted"
    CHANGED = "changed"  # the staging object is not the one that was checked (412)
    SOURCE_GONE = "source_gone"  # a concurrent completion already promoted and deleted it


class FailureReason(StrEnum):
    """Why a version ended `failed`; shown to people, so stable and human-mappable."""

    UPLOAD_CHANGED = "UPLOAD_CHANGED"
    UNREADABLE_IMAGE = "UNREADABLE_IMAGE"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    PROCESSING_GAVE_UP = "PROCESSING_GAVE_UP"
    UPLOAD_EXPIRED = "UPLOAD_EXPIRED"  # never completed within UPLOAD_ABANDONED_AFTER_HOURS
    UNREADABLE_MODEL = "UNREADABLE_MODEL"
    MODEL_TOO_LARGE = "MODEL_TOO_LARGE"


class JobKind(StrEnum):
    """Work the worker knows how to do."""

    THUMBNAIL = "thumbnail"


class JobStatus(StrEnum):
    """Life cycle of a queued job."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    DEAD = "dead"


class CircuitState(StrEnum):
    """State of the storage circuit breaker (KILN-23)."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class FastFailCause(StrEnum):
    """Why a storage call was refused without asking storage (KILN-23); logs only."""

    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    BULKHEAD_FULL = "BULKHEAD_FULL"


class Scope(StrEnum):
    """What a personal access token may do; a browser session has every scope (KILN-12)."""

    READ = "read"
    WRITE = "write"


class AuthMethod(StrEnum):
    """How a request proved who it is."""

    SESSION = "session"
    TOKEN = "token"  # noqa: S105 - a method name, not a secret


class Action(StrEnum):
    """Everything the authorization policy decides on; one place for every check (ADR 0012)."""

    READ_ASSETS = "read_assets"
    WRITE_ASSETS = "write_assets"
    MANAGE_TOKENS = "manage_tokens"
    READ_COMMENTS = "read_comments"
    WRITE_COMMENTS = "write_comments"  # start, reply, resolve, reopen
    CHANGE_OWN_COMMENT = "change_own_comment"  # edit or delete: the author only
    READ_REVIEWS = "read_reviews"  # a version's review state and history (KILN-11)
    REVIEW_VERSIONS = "review_versions"  # approve, request changes, reopen


class RegionShape(StrEnum):
    """What a comment marks on an image (KILN-10)."""

    RECT = "rect"
    POINT = "point"


class ReviewState(StrEnum):
    """Where a version stands in review (KILN-11); every version starts in review."""

    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class ReviewAction(StrEnum):
    """What a reviewer does to a version's review state (KILN-11)."""

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REOPEN = "reopen"
