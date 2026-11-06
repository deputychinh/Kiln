"""The single mapping from errors to RFC 9457 problem details, at the HTTP boundary."""

import logging
from http import HTTPStatus
from typing import Any, TypedDict, Unpack

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kiln_api.constants import (
    DB_BUSY_SQLSTATES,
    MAX_JSON_BODY_BYTES,
    PROBLEM_JSON,
    RETRY_AFTER_SECONDS,
)
from kiln_api.enums import ErrorCode, FastFailCause
from kiln_api.errors import DatabaseUnavailableError, DomainError
from kiln_api.schemas.problems import Problem

logger = logging.getLogger("kiln_api")

_HTTP_CODES = {
    HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: ErrorCode.PAYLOAD_TOO_LARGE,
}


class _Options(TypedDict, total=False):
    extra: dict[str, object]
    headers: dict[str, str]


def _problem(
    request: Request, status: HTTPStatus, code: ErrorCode, detail: str, **options: Unpack[_Options]
) -> JSONResponse:
    body: dict[str, object] = {
        "type": "about:blank",
        "title": status.phrase,
        "status": status.value,
        "detail": detail,
        "instance": request.url.path,
        "code": code.value,
        **options.get("extra", {}),
    }
    merged = dict(options.get("headers", {}))
    if status == HTTPStatus.SERVICE_UNAVAILABLE:
        merged.setdefault("Retry-After", str(RETRY_AFTER_SECONDS))
    return JSONResponse(body, status_code=status.value, media_type=PROBLEM_JSON, headers=merged)


async def _domain_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)  # noqa: S101 - registered only for DomainError
    if exc.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        # A refused storage call is expected during an outage: the breaker logged it once.
        fast_fail = exc.cause_code in set(FastFailCause)
        logger.log(
            logging.DEBUG if fast_fail else logging.ERROR,
            "%s on %s (request %s, cause %s)",
            exc.code.value,
            request.url.path,
            getattr(request.state, "request_id", "-"),
            exc.cause_code or "-",
        )
    retry_after = getattr(exc, "retry_after_seconds", None)
    headers = {} if retry_after is None else {"Retry-After": str(retry_after)}
    return _problem(request, exc.status, exc.code, exc.detail, headers=headers)


async def _http_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 - registered only for it
    status = HTTPStatus(exc.status_code)
    return _problem(
        request,
        status,
        _HTTP_CODES.get(status, ErrorCode.INTERNAL),
        str(exc.detail),
        headers=dict(exc.headers or {}),
    )


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - registered only for it
    errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return _problem(
        request,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        ErrorCode.VALIDATION_FAILED,
        "The request is not valid.",
        extra={"errors": errors},
    )


async def _database_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, SQLAlchemyError)  # noqa: S101 - registered only for it
    sqlstate = (
        getattr(getattr(exc, "orig", None), "sqlstate", None)
        if isinstance(exc, DBAPIError)
        else None
    )
    if sqlstate in DB_BUSY_SQLSTATES:
        logger.warning("database busy (%s) on %s", sqlstate, request.url.path)
        return _problem(
            request,
            HTTPStatus.SERVICE_UNAVAILABLE,
            ErrorCode.DATABASE_BUSY,
            "The database is busy; retry shortly.",
        )
    logger.error("database error on %s: %s", request.url.path, type(exc).__name__)
    unavailable = DatabaseUnavailableError()
    return _problem(request, unavailable.status, unavailable.code, unavailable.detail)


def unexpected_problem(request: Request, exc: Exception) -> JSONResponse:
    """Log an unforeseen error with the request id and answer 500 without internals.

    Called from the request-id middleware so the response still passes through CORS and
    carries `X-Request-Id`, which a handler run by Starlette's outermost middleware would not.
    """
    logger.error(
        "unexpected error on %s (request %s)",
        request.url.path,
        getattr(request.state, "request_id", "-"),
        exc_info=exc,
    )
    return _problem(
        request,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL,
        "Something went wrong on our side.",
    )


async def _read_limited(receive: Receive) -> bytes | None:
    """Buffer a chunked body; None as soon as it passes `MAX_JSON_BODY_BYTES`."""
    chunks: list[bytes] = []
    size = 0
    more = True
    while more:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_JSON_BODY_BYTES:
            return None
        chunks.append(chunk)
        more = message.get("more_body", False)
    return b"".join(chunks)


class BodySizeLimit:
    """Reject request bodies over `MAX_JSON_BODY_BYTES` with 413 before they are parsed."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap `app`."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Check `Content-Length`, then count streamed bytes for chunked bodies."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_JSON_BODY_BYTES:
            await self._reject(scope, receive, send)
            return
        if declared is not None:
            await self._app(scope, receive, send)
            return
        body = await _read_limited(receive)
        if body is None:
            await self._reject(scope, receive, send)
            return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self._app(scope, replay, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = _problem(
            Request(scope, receive),
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            ErrorCode.PAYLOAD_TOO_LARGE,
            "Request body over 1 MB.",
        )
        await response(scope, receive, send)


def install_error_handlers(app: FastAPI) -> None:
    """Map every error to problem details exactly once, at the boundary."""
    app.add_exception_handler(DomainError, _domain_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(SQLAlchemyError, _database_handler)


def install_problem_schema(app: FastAPI) -> None:
    """Publish the `Problem` schema that every error response references."""
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = build()
        problem = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.update(problem.pop("$defs", {}))
        components["Problem"] = problem
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
