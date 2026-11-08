"""RFC 9457 problem details as documented in OpenAPI."""

from http import HTTPStatus
from typing import Any

from pydantic import BaseModel, Field

from kiln_api.constants import PROBLEM_JSON
from kiln_api.enums import ErrorCode, ReviewState


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
    current_state: ReviewState | None = Field(
        default=None,
        description=(
            "On `REVIEW_STATE_CONFLICT` and `INVALID_REVIEW_TRANSITION`: the version's review"
            " state now (KILN-11)."
        ),
    )
    current_revision: int | None = Field(
        default=None,
        description="On `REVIEW_STATE_CONFLICT`: the version's review revision now (KILN-11).",
    )


_DESCRIPTIONS = {
    400: "Malformed request: an invalid cursor or Idempotency-Key (see `code`).",
    401: (
        "Not signed in: no session cookie or bearer token, or it is unknown, expired or revoked"
        " (`UNAUTHENTICATED`); on sign-in, a wrong email or password (`INVALID_CREDENTIALS`)."
    ),
    403: (
        "Signed in but not allowed: the token lacks the scope (`INSUFFICIENT_SCOPE`), the action"
        " needs a browser session (`SESSION_REQUIRED`), or a cookie-authenticated write failed"
        " the CSRF check (`CSRF_CHECK_FAILED`)."
    ),
    404: "The resource does not exist.",
    409: (
        "Conflict with the current state: upload missing or different, the Idempotency-Key"
        " is still in use, too many active access tokens, or a review decision that no longer"
        " applies (`REVIEW_STATE_CONFLICT`, `INVALID_REVIEW_TRANSITION`, `VERSION_NOT_READY`)."
    ),
    413: "Request body larger than 1 MB.",
    422: "Validation failed: a field or a domain rule (see `code`).",
    429: "Too many failed sign-ins for this account or address; retry after `Retry-After`.",
    503: "Database or storage unavailable or busy; retry after `Retry-After`.",
}


_PROBLEM_REF = {"$ref": "#/components/schemas/Problem"}
RETRY_AFTER_HEADER = {
    "Retry-After": {
        "description": "Seconds to wait before retrying.",
        "schema": {"type": "integer"},
    }
}
WWW_AUTHENTICATE_HEADER = {
    "WWW-Authenticate": {
        "description": "The scheme to use: `Bearer` with a personal access token.",
        "schema": {"type": "string"},
    }
}
LOCATION_HEADER = {
    "Location": {"description": "URL of the created resource.", "schema": {"type": "string"}}
}
CREATED_HEADERS = {
    **LOCATION_HEADER,
    "Idempotent-Replayed": {
        "description": "`true` when this response replays an earlier request with the same key.",
        "schema": {"type": "string", "enum": ["true"]},
    },
}


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries: only `application/problem+json`, with `Retry-After` on 503."""
    responses: dict[int | str, dict[str, Any]] = {}
    for status in statuses:
        entry: dict[str, Any] = {
            "description": _DESCRIPTIONS[status],
            "content": {PROBLEM_JSON: {"schema": _PROBLEM_REF}},
        }
        if status in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.TOO_MANY_REQUESTS}:
            entry["headers"] = RETRY_AFTER_HEADER
        elif status == HTTPStatus.UNAUTHORIZED:
            entry["headers"] = WWW_AUTHENTICATE_HEADER
        responses[status] = entry
    return responses
