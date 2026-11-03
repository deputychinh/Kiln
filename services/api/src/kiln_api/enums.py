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


class HealthStatus(StrEnum):
    """Result of a health or readiness probe."""

    OK = "ok"
