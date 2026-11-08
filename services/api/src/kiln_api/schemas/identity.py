"""Request and response bodies for sign-in, the current user and access tokens (KILN-12)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from kiln_api.constants import (
    ACCESS_TOKEN_NAME_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    PASSWORD_INPUT_MAX_LENGTH,
)
from kiln_api.domain.identity import AccessToken, Principal
from kiln_api.enums import AuthMethod, Scope

# Edge bounds only: the domain gives the precise rule; long input is cut before hashing.
_FIELD_SLACK = 4


class SignInRequest(BaseModel):
    """Email and password; never logged."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=EMAIL_MAX_LENGTH * _FIELD_SLACK)
    password: str = Field(min_length=1, max_length=PASSWORD_INPUT_MAX_LENGTH)


class MeOut(BaseModel):
    """The signed-in user and how the request was authenticated."""

    id: UUID
    email: str
    display_name: str
    auth_method: AuthMethod
    scopes: list[Scope]

    @classmethod
    def of(cls, principal: Principal) -> "MeOut":
        """Map a principal."""
        return cls(
            id=principal.user_id,
            email=principal.email,
            display_name=principal.display_name,
            auth_method=principal.method,
            scopes=sorted(principal.scopes),
        )


class CreateTokenRequest(BaseModel):
    """A name people recognise, the scopes and one of the offered lifetimes."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=ACCESS_TOKEN_NAME_MAX_LENGTH * _FIELD_SLACK)
    scopes: list[Scope] = Field(min_length=1, max_length=len(Scope))
    expires_in_days: Literal[7, 30, 90, 365]


class TokenOut(BaseModel):
    """A token as listed: never its secret."""

    id: UUID
    name: str
    prefix: str
    scopes: list[Scope]
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None

    @classmethod
    def of(cls, token: AccessToken) -> "TokenOut":
        """Map a stored token."""
        return cls(
            id=token.id,
            name=token.name,
            prefix=token.prefix,
            scopes=sorted(token.scopes),
            created_at=token.created_at,
            expires_at=token.expires_at,
            last_used_at=token.last_used_at,
        )


class TokenListOut(BaseModel):
    """The caller's tokens that are not revoked, newest first."""

    items: list[TokenOut]


class CreatedTokenOut(TokenOut):
    """A new token with its secret, shown in this response only."""

    token: str
