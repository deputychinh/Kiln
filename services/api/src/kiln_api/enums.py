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
