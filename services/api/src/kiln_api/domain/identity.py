"""Users, sessions and personal access tokens (KILN-12): rules only, no I/O."""

import hashlib
import re
import secrets
import unicodedata
from collections.abc import Container
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from kiln_api.constants import (
    ACCESS_TOKEN_BYTES,
    ACCESS_TOKEN_EXPIRY_DAYS,
    ACCESS_TOKEN_NAME_MAX_LENGTH,
    ACCESS_TOKEN_PREFIX,
    ACCESS_TOKEN_SHOWN_PREFIX_LENGTH,
    DISPLAY_NAME_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    PASSWORD_CONTEXT_WORD_MIN_LENGTH,
    PASSWORD_CONTEXT_WORDS,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    SESSION_ABSOLUTE_HOURS,
    SESSION_ID_BYTES,
    SESSION_IDLE_MINUTES,
)
from kiln_api.domain.assets import IdFactory, is_unreadable
from kiln_api.enums import AuthMethod, Scope
from kiln_api.errors import (
    CommonPasswordError,
    GuessablePasswordError,
    InvalidDisplayNameError,
    InvalidEmailError,
    InvalidTokenNameError,
    WeakPasswordError,
)

# One `@`, no spaces, a dot in the domain: enough to catch typos; the operator types these.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# What an access token looks like on the wire; anything else is refused without a lookup.
# Where an email's local part splits into the words people reuse ("ada.lovelace" → ada, lovelace).
_WORD_BREAK = re.compile(r"[\W_]+")
_TOKEN = re.compile(rf"^{ACCESS_TOKEN_PREFIX}[A-Za-z0-9_-]{{43}}$")
SESSION_IDLE = timedelta(minutes=SESSION_IDLE_MINUTES)
SESSION_ABSOLUTE = timedelta(hours=SESSION_ABSOLUTE_HOURS)
ALL_SCOPES = frozenset(Scope)


@dataclass(frozen=True, slots=True)
class User:
    """Someone who can sign in; `password_hash` is an Argon2id PHC string."""

    id: UUID
    email: str
    display_name: str
    password_hash: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is calling and what they may do; built per request from a session or a token."""

    user_id: UUID
    email: str
    display_name: str
    method: AuthMethod
    scopes: frozenset[Scope]
    token_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Session:
    """A signed-in browser; only the SHA-256 of its id is stored."""

    id_hash: bytes
    user_id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime  # the absolute bound, fixed at sign-in

    def is_live(self, now: datetime) -> bool:
        """Neither idle too long nor past its absolute bound."""
        return now < self.expires_at and now < self.last_seen_at + SESSION_IDLE


@dataclass(frozen=True, slots=True)
class AccessToken:
    """A personal access token for the CLI or Blender; only its SHA-256 is stored."""

    id: UUID
    user_id: UUID
    name: str
    prefix: str  # the first characters, shown so people can tell tokens apart
    token_hash: bytes
    scopes: frozenset[Scope]
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    def is_live(self, now: datetime) -> bool:
        """Not revoked and not expired."""
        return self.revoked_at is None and now < self.expires_at


def normalize_email(raw: str) -> str:
    """Trim and lower-case an email; raise `InvalidEmailError` when it cannot be one."""
    email = raw.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL.match(email) or is_unreadable(email):
        raise InvalidEmailError
    return email


def clean_display_name(raw: str) -> str:
    """Trim a display name; raise `InvalidDisplayNameError` when it breaks the rules."""
    name = raw.strip()
    if not name or len(name) > DISPLAY_NAME_MAX_LENGTH or is_unreadable(name):
        raise InvalidDisplayNameError
    return name


def normalize_password(password: str) -> str:
    """NFKC (NIST SP 800-63B 5.1.1.2), so "é" typed as one or two code points is one password."""
    return unicodedata.normalize("NFKC", password)


def password_key(password: str) -> str:
    """How a password is compared with the blocklist and context words: NFKC, case-folded, NFKC.

    Unicode's NFKC_Casefold, so "PASSWORD", "password" and its full-width form are one
    entry. Used only for comparing; the stored hash keeps the case (`normalize_password`).
    """
    return unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", password).casefold())


def password_context_words(email: str) -> tuple[str, ...]:
    """The words a new password must not lean on: "kiln", the email's local part and its pieces.

    Longest first, so a whole local part is removed before its pieces.
    """
    local = password_key(email.rpartition("@")[0])
    words = {*PASSWORD_CONTEXT_WORDS, local, *_WORD_BREAK.split(local)}
    kept = (word for word in words if len(word) >= PASSWORD_CONTEXT_WORD_MIN_LENGTH)
    return tuple(sorted(kept, key=lambda word: (-len(word), word)))


def _without(key: str, words: tuple[str, ...]) -> str:
    """`key` with every context word removed, repeated until none is left ("kikilnln" → "")."""
    while True:
        rest = key
        for word in words:
            rest = rest.replace(word, "")
        if rest == key:
            return rest
        key = rest


def check_new_password(password: str, *, email: str, blocklist: Container[str]) -> None:
    """Refuse a password being chosen (ASVS 5.0 V6.2, NIST SP 800-63B-4 3.1.1.2).

    Length only for composition (no character-class rules, never trimmed), counted after NFKC as
    it is stored; then the bundled list of common and breached passwords (`blocklist` holds
    `password_key` forms); then context: what is left without "kiln" and the email's local part
    must still reach the minimum length and not be on the list. Never called at sign-in, so
    passwords chosen under older rules keep working (ADR 0017).
    """
    if not PASSWORD_MIN_LENGTH <= len(normalize_password(password)) <= PASSWORD_MAX_LENGTH:
        raise WeakPasswordError
    key = password_key(password)
    if key in blocklist:
        raise CommonPasswordError
    rest = _without(key, password_context_words(email))
    if len(rest) < PASSWORD_MIN_LENGTH or rest in blocklist:
        raise GuessablePasswordError


def clean_token_name(raw: str) -> str:
    """Trim a token name; raise `InvalidTokenNameError` when it breaks the rules."""
    name = raw.strip()
    if not name or len(name) > ACCESS_TOKEN_NAME_MAX_LENGTH or is_unreadable(name):
        raise InvalidTokenNameError
    return name


def secret_hash(secret: str) -> bytes:
    """SHA-256 of a high-entropy secret; enough for random 256-bit values (no salt needed)."""
    return hashlib.sha256(secret.encode()).digest()


def account_key(email: str) -> bytes:
    """What sign-in throttling counts failures under: never the email itself."""
    return hashlib.sha256(f"sign-in:{email.strip().lower()}".encode()).digest()


def looks_like_access_token(value: str) -> bool:
    """True for strings shaped like a Kiln token; others are refused before any lookup."""
    return bool(_TOKEN.match(value))


def new_session(user_id: UUID, *, now: datetime) -> tuple[str, Session]:
    """A fresh random session id (returned once, for the cookie) and the record to store."""
    raw = secrets.token_urlsafe(SESSION_ID_BYTES)
    session = Session(
        id_hash=secret_hash(raw),
        user_id=user_id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + SESSION_ABSOLUTE,
    )
    return raw, session


def new_access_token(  # noqa: PLR0913 - keyword-only facts of one token
    user_id: UUID,
    *,
    name: str,
    scopes: frozenset[Scope],
    expires_in_days: int,
    now: datetime,
    new_id: IdFactory,
) -> tuple[str, AccessToken]:
    """A fresh token (returned once) and the record to store.

    Raises:
        InvalidTokenNameError: The name breaks the rules.
        ValueError: No scope, or an expiry Kiln does not offer (the API validates both first).
    """
    if not scopes or not scopes <= ALL_SCOPES:
        msg = "A token needs at least one known scope."
        raise ValueError(msg)
    if expires_in_days not in ACCESS_TOKEN_EXPIRY_DAYS:
        msg = f"Tokens expire after one of {ACCESS_TOKEN_EXPIRY_DAYS} days."
        raise ValueError(msg)
    raw = ACCESS_TOKEN_PREFIX + secrets.token_urlsafe(ACCESS_TOKEN_BYTES)
    token = AccessToken(
        id=new_id(),
        user_id=user_id,
        name=clean_token_name(name),
        prefix=raw[:ACCESS_TOKEN_SHOWN_PREFIX_LENGTH],
        token_hash=secret_hash(raw),
        scopes=scopes,
        created_at=now,
        expires_at=now + timedelta(days=expires_in_days),
    )
    return raw, token


def session_principal(user: User) -> Principal:
    """A signed-in browser may do everything a token could."""
    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        method=AuthMethod.SESSION,
        scopes=ALL_SCOPES,
    )


def token_principal(user: User, token: AccessToken) -> Principal:
    """A token may do only what its scopes allow."""
    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        method=AuthMethod.TOKEN,
        scopes=token.scopes,
        token_id=token.id,
    )
