"""The single mapping from errors to RFC 9457 problem details, at the HTTP boundary."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from kiln_api.constants import PROBLEM_JSON
from kiln_api.enums import ErrorCode
from kiln_api.errors import DomainError


def _problem(
    request: Request,
    status: HTTPStatus,
    code: ErrorCode,
    detail: str,
    extra: dict[str, object] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {
        "type": "about:blank",
        "title": status.phrase,
        "status": status.value,
        "detail": detail,
        "instance": request.url.path,
        "code": code.value,
        **(extra or {}),
    }
    return JSONResponse(body, status_code=status.value, media_type=PROBLEM_JSON)


async def _domain_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)  # noqa: S101 - registered only for DomainError
    return _problem(request, exc.status, exc.code, exc.detail)


async def _http_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 - registered only for it
    status = HTTPStatus(exc.status_code)
    code = ErrorCode.NOT_FOUND if status == HTTPStatus.NOT_FOUND else ErrorCode.INTERNAL
    return _problem(request, status, code, str(exc.detail))


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - registered only for it
    errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return _problem(
        request,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        ErrorCode.VALIDATION_FAILED,
        "The request is not valid.",
        {"errors": errors},
    )


def install_error_handlers(app: FastAPI) -> None:
    """Map every handled error to problem details exactly once, at the boundary."""
    app.add_exception_handler(DomainError, _domain_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
