"""RFC 9457 problem details as documented in OpenAPI."""

from http import HTTPStatus
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


_PROBLEM_REF = {"$ref": "#/components/schemas/Problem"}
RETRY_AFTER_HEADER = {
    "Retry-After": {
        "description": "Seconds to wait before retrying.",
        "schema": {"type": "integer"},
    }
}
LOCATION_HEADER = {
    "Location": {"description": "URL of the created resource.", "schema": {"type": "string"}}
}


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries: only `application/problem+json`, with `Retry-After` on 503."""
    responses: dict[int | str, dict[str, Any]] = {}
    for status in statuses:
        entry: dict[str, Any] = {
            "description": _DESCRIPTIONS[status],
            "content": {PROBLEM_JSON: {"schema": _PROBLEM_REF}},
        }
        if status == HTTPStatus.SERVICE_UNAVAILABLE:
            entry["headers"] = RETRY_AFTER_HEADER
        responses[status] = entry
    return responses
