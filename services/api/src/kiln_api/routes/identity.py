"""Sign-in, sign-out, the current user and personal access tokens (`/api/v1`, KILN-12)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from kiln_api.authentication import (
    Authenticated,
    check_app_origin,
    client_ip,
    identity_of,
    settings_of,
)
from kiln_api.constants import API_PREFIX, SESSION_ABSOLUTE_HOURS
from kiln_api.schemas.identity import (
    CreatedTokenOut,
    CreateTokenRequest,
    MeOut,
    SignInRequest,
    TokenListOut,
    TokenOut,
)
from kiln_api.schemas.problems import CREATED_HEADERS, problem_responses
from kiln_api.services.identity import IdentityService

router = APIRouter(prefix=API_PREFIX, tags=["identity"], responses=problem_responses(413, 422, 503))
Identity = Annotated[IdentityService, Depends(identity_of)]
_SESSION_MAX_AGE = SESSION_ABSOLUTE_HOURS * 60 * 60
_CURRENT_SESSION = f"{API_PREFIX}/sessions/current"


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_app_origin)],
    responses={
        201: {"description": "Signed in; the session cookie is set.", "headers": CREATED_HEADERS},
        **problem_responses(401, 403, 429),
    },
)
def sign_in(body: SignInRequest, request: Request, response: Response, identity: Identity) -> MeOut:
    """Sign in with email and password; a new session replaces any current one.

    The cookie is `HttpOnly`, `SameSite=Lax`, `Path=/`, and `Secure` with the `__Host-` prefix
    over HTTPS. Writes from the browser need the `X-Kiln-Csrf: 1` header and an allowed Origin.
    """
    settings = settings_of(request)
    cookie = settings.session_cookie_name
    signed = identity.sign_in(
        body.email,
        body.password,
        client_ip=client_ip(request),
        previous_session=request.cookies.get(cookie),
    )
    response.set_cookie(
        cookie,
        signed.session_id,
        max_age=_SESSION_MAX_AGE,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Location"] = _CURRENT_SESSION
    return MeOut.of(signed.principal)


@router.delete(
    "/sessions/current",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_app_origin)],
    responses=problem_responses(403),
)
def sign_out(request: Request, identity: Identity) -> Response:
    """End the current session and clear the cookie; safe to repeat."""
    settings = settings_of(request)
    identity.sign_out(request.cookies.get(settings.session_cookie_name))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me", responses=problem_responses(401))
def me(principal: Authenticated) -> MeOut:
    """The signed-in user (session or token) and the scopes of this request."""
    return MeOut.of(principal)


@router.get("/me/tokens", responses=problem_responses(401, 403))
def list_tokens(principal: Authenticated, identity: Identity) -> TokenListOut:
    """Your access tokens that are not revoked, newest first; secrets are never returned."""
    return TokenListOut(items=[TokenOut.of(t) for t in identity.list_tokens(principal)])


@router.post(
    "/me/tokens",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Created; `token` is shown only now.", "headers": CREATED_HEADERS},
        **problem_responses(401, 403, 409),
    },
)
def create_token(
    body: CreateTokenRequest, principal: Authenticated, identity: Identity, response: Response
) -> CreatedTokenOut:
    """Create a personal access token for the CLI or Blender (browser session only)."""
    issued = identity.create_token(
        principal,
        name=body.name,
        scopes=frozenset(body.scopes),
        expires_in_days=body.expires_in_days,
    )
    response.headers["Location"] = f"{API_PREFIX}/me/tokens/{issued.token.id}"
    return CreatedTokenOut(**TokenOut.of(issued.token).model_dump(), token=issued.secret)


@router.delete(
    "/me/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(401, 403, 404),
)
def revoke_token(token_id: UUID, principal: Authenticated, identity: Identity) -> Response:
    """Revoke one of your tokens; it stops working at once."""
    identity.revoke_token(principal, token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
