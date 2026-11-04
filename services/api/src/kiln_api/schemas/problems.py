"""RFC 9457 problem details as documented in OpenAPI."""

from typing import Any

from pydantic import BaseModel

from kiln_api.constants import PROBLEM_JSON
from kiln_api.enums import ErrorCode


class FieldError(BaseModel):
    """One invalid field of a request."""

    loc: list[str | int]
    msg: str


class Problem(BaseModel):
    """Every error response: `code` is stable, the rest is for people."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    code: ErrorCode
    errors: list[FieldError] | None = None


_DESCRIPTIONS = {
    400: "Malformed request, for example an invalid cursor.",
    404: "The resource does not exist.",
    409: "Conflict with the current state (upload missing or different).",
    413: "Request body larger than 1 MB.",
    422: "Validation failed: a field or a domain rule (see `code`).",
    503: "Database or storage unavailable or busy; retry after `Retry-After`.",
}


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries for the given error statuses."""
    return {
        status: {
            "model": Problem,
            "description": _DESCRIPTIONS[status],
            "content": {PROBLEM_JSON: {}},
        }
        for status in statuses
    }
