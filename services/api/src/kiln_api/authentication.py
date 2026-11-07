"""Who is calling (KILN-12): a session cookie or a bearer token, plus the CSRF check.

Every route outside `/health` and `/ready` depends on `authenticate`; `test_every_route_needs_a_
principal` enumerates the app's routes to keep it that way.
"""

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from kiln_api.config import Settings
from kiln_api.constants import (
    CSRF_HEADER,
    CSRF_HEADER_VALUE,
    SAFE_METHODS,
    SESSION_COOKIE_LOCAL,
)
from kiln_api.domain.identity import Principal
from kiln_api.errors import CsrfCheckFailedError, UnauthenticatedError
from kiln_api.services.identity import IdentityService

# Documentation only (OpenAPI security schemes); `authenticate` reads the request itself.
_BEARER_SCHEME = HTTPBearer(
    scheme_name="accessToken",
    description="A personal access token (`kiln_pat_…`) for the CLI and Blender.",
    auto_error=False,
)
_COOKIE_SCHEME = APIKeyCookie(
    name=SESSION_COOKIE_LOCAL,
    scheme_name="sessionCookie",
    description=(
        "The browser session from `POST /api/v1/sessions` (`__Host-kiln_session` over HTTPS)."
        " Writes also need `X-Kiln-Csrf: 1` and an allowed Origin."
    ),
    auto_error=False,
)
_SAME_ORIGIN = "same-origin"
_BEARER = "bearer"


def settings_of(request: Request) -> Settings:
    """The settings the app was built with."""
    settings: Settings = request.app.state.settings
    return settings


def identity_of(request: Request) -> IdentityService:
    """The identity service of the running container."""
    service: IdentityService = request.app.state.container.identity
    return service


def client_ip(request: Request) -> str:
    """The peer address; behind a proxy, run uvicorn with `--proxy-headers` and its allow-list."""
    return request.client.host if request.client else "unknown"


def check_app_origin(request: Request) -> None:
    """CSRF defence for cookie-authenticated writes (OWASP CSRF Prevention Cheat Sheet).

    A custom header a cross-site page cannot send without a CORS preflight (which the API refuses
    for origins it does not list), plus an Origin from the allow-list; when a browser omits
    Origin, Fetch Metadata must say same-origin. SameSite=Lax on the cookie is defence in depth.
    """
    if request.method in SAFE_METHODS:
        return
    if request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
        raise CsrfCheckFailedError
    origin = request.headers.get("origin")
    if origin is None:
        if request.headers.get("sec-fetch-site") != _SAME_ORIGIN:
            raise CsrfCheckFailedError
    elif origin not in settings_of(request).trusted_origins:
        raise CsrfCheckFailedError


def authenticate(
    request: Request,
    _token: Annotated[HTTPAuthorizationCredentials | None, Security(_BEARER_SCHEME)] = None,
    _cookie: Annotated[str | None, Security(_COOKIE_SCHEME)] = None,
) -> Principal:
    """A bearer token when an Authorization header is sent, else the session cookie.

    A bad token is refused even if a cookie is present; tokens carry no ambient authority, so
    only cookie-authenticated writes need the CSRF check.
    """
    identity = identity_of(request)
    authorization = request.headers.get("authorization")
    if authorization is not None:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() != _BEARER or not credentials.strip():
            raise UnauthenticatedError
        return identity.authenticate_token(credentials.strip())
    session_id = request.cookies.get(settings_of(request).session_cookie_name)
    if session_id is None:
        raise UnauthenticatedError
    principal = identity.authenticate_session(session_id)
    check_app_origin(request)
    return principal


Authenticated = Annotated[Principal, Depends(authenticate)]
