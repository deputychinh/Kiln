"""Identity use cases (KILN-12): users, sign-in and sign-out, sessions, access tokens."""

import logging
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from kiln_api.constants import (
    ACCESS_TOKEN_MAX_PER_USER,
    ACCESS_TOKEN_TOUCH_SECONDS,
    SESSION_ID_BYTES,
    SESSION_TOUCH_SECONDS,
    SIGN_IN_MAX_FAILURES_PER_ACCOUNT,
    SIGN_IN_MAX_FAILURES_PER_IP,
    SIGN_IN_WINDOW_MINUTES,
)
from kiln_api.domain.assets import IdFactory
from kiln_api.domain.authorization import authorize
from kiln_api.domain.identity import (
    SESSION_IDLE,
    AccessToken,
    Principal,
    User,
    account_key,
    check_new_password,
    clean_display_name,
    looks_like_access_token,
    new_access_token,
    new_session,
    normalize_email,
    secret_hash,
    session_principal,
    token_principal,
)
from kiln_api.enums import Action, Scope
from kiln_api.errors import (
    AccessTokenLimitError,
    AccessTokenNotFoundError,
    InvalidCredentialsError,
    InvalidEmailError,
    SignInThrottledError,
    UnauthenticatedError,
)
from kiln_api.ports import Clock, FailureCounts, IdentityStore, PasswordHasher

logger = logging.getLogger("kiln_api.security")

_WINDOW = timedelta(minutes=SIGN_IN_WINDOW_MINUTES)
_SESSION_TOUCH = timedelta(seconds=SESSION_TOUCH_SECONDS)
_TOKEN_TOUCH = timedelta(seconds=ACCESS_TOKEN_TOUCH_SECONDS)
# token_urlsafe(32) is 43 characters; anything much longer is not ours and is never looked up.
_SESSION_ID_MAX_LENGTH = SESSION_ID_BYTES * 2
_TOKEN_LIST_LIMIT = ACCESS_TOKEN_MAX_PER_USER * 2


@dataclass(frozen=True, slots=True)
class SignedIn:
    """A new session: the cookie value (shown once) and who it belongs to."""

    session_id: str
    principal: Principal
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """A new access token: the secret (shown once) and its stored record."""

    secret: str
    token: AccessToken


class IdentityService:
    """Coordinates the identity store, the password hasher and the clock."""

    def __init__(
        self,
        store: IdentityStore,
        hasher: PasswordHasher,
        clock: Clock,
        new_id: IdFactory,
    ) -> None:
        """Receive collaborators; hash a random password so unknown emails cost the same."""
        self._store = store
        self._hasher = hasher
        self._clock = clock
        self._new_id = new_id
        self._dummy_hash = hasher.hash(secrets.token_urlsafe(SESSION_ID_BYTES))

    # --- users ------------------------------------------------------------------------------

    def create_user(self, email: str, display_name: str, password: str) -> User:
        """Create a user (the operator's `make create-user`; there is no public sign-up)."""
        check_new_password(password)
        now = self._clock.now()
        user = User(
            id=self._new_id(),
            email=normalize_email(email),
            display_name=clean_display_name(display_name),
            password_hash=self._hasher.hash(password),
            created_at=now,
            updated_at=now,
        )
        self._store.add_user(user)
        logger.info("user created (user %s)", user.id)
        return user

    # --- sessions ---------------------------------------------------------------------------

    def sign_in(
        self, email: str, password: str, *, client_ip: str, previous_session: str | None = None
    ) -> SignedIn:
        """Check the password and open a new session; the old one (if any) ends (rotation).

        Unknown emails and wrong passwords take the same path, the same hash work and the same
        answer. Failures count per account (existing or not) and per IP.

        Raises:
            SignInThrottledError: Too many recent failures for the account or the IP.
            InvalidCredentialsError: Unknown email or wrong password.
        """
        now = self._clock.now()
        key = account_key(email)
        # Counted before the password is checked, under per-account and per-IP locks: parallel
        # attempts can never check more passwords than the limits (review V2).
        self._reserve_attempt(key, client_ip, now)
        user = self._user_for(email)
        password_ok = self._hasher.verify(
            self._dummy_hash if user is None else user.password_hash, password
        )
        if user is None or not password_ok:
            logger.warning("sign-in failed (account key %s)", key.hex()[:12])
            raise InvalidCredentialsError  # the reserved attempt stays as the failure
        self._store.clear_failures(key)  # the reservation and earlier failures
        if self._hasher.needs_rehash(user.password_hash):
            self._store.set_password_hash(user.id, self._hasher.hash(password), now=now)
        if previous_session is not None:
            self._store.delete_session(secret_hash(previous_session))
        self._store.purge_sessions(now=now, idle=SESSION_IDLE)
        raw, session = new_session(user.id, now=now)
        self._store.add_session(session)
        logger.info("signed in (user %s)", user.id)
        return SignedIn(
            session_id=raw, principal=session_principal(user), expires_at=session.expires_at
        )

    def _user_for(self, email: str) -> User | None:
        try:
            return self._store.user_by_email(normalize_email(email))
        except InvalidEmailError:
            return None  # same path as an unknown account

    def _reserve_attempt(self, key: bytes, client_ip: str, now: datetime) -> None:
        counts = self._store.reserve_attempt(
            attempt_id=self._new_id(),
            account_key=key,
            client_ip=client_ip,
            now=now,
            since=now - _WINDOW,
            limits=(SIGN_IN_MAX_FAILURES_PER_ACCOUNT, SIGN_IN_MAX_FAILURES_PER_IP),
        )
        oldest = None if counts is None else _blocking_oldest(counts)
        if oldest is None:
            return
        wait = max(1, math.ceil((oldest + _WINDOW - now).total_seconds()))
        logger.warning("sign-in throttled (account key %s)", key.hex()[:12])
        raise SignInThrottledError(retry_after_seconds=wait)

    def sign_out(self, session_id: str | None) -> None:
        """End the session if there is one; always succeeds."""
        if session_id is not None and len(session_id) <= _SESSION_ID_MAX_LENGTH:
            self._store.delete_session(secret_hash(session_id))

    def authenticate_session(self, session_id: str) -> Principal:
        """The principal of a live session; an idle or expired one is deleted."""
        if len(session_id) > _SESSION_ID_MAX_LENGTH:
            raise UnauthenticatedError
        id_hash = secret_hash(session_id)
        found = self._store.session_user(id_hash)
        if found is None:
            raise UnauthenticatedError
        session, user = found
        now = self._clock.now()
        if not session.is_live(now):
            self._store.delete_session(id_hash)
            raise UnauthenticatedError
        if now - session.last_seen_at >= _SESSION_TOUCH:
            self._store.touch_session(id_hash, now=now)
        return session_principal(user)

    # --- access tokens ----------------------------------------------------------------------

    def authenticate_token(self, secret: str) -> Principal:
        """The principal of a live access token (scoped)."""
        if not looks_like_access_token(secret):
            raise UnauthenticatedError
        found = self._store.token_user(secret_hash(secret))
        if found is None:
            raise UnauthenticatedError
        token, user = found
        now = self._clock.now()
        if not token.is_live(now):
            raise UnauthenticatedError
        if token.last_used_at is None or now - token.last_used_at >= _TOKEN_TOUCH:
            self._store.touch_token(token.id, now=now)
        return token_principal(user, token)

    def list_tokens(self, principal: Principal) -> list[AccessToken]:
        """The caller's tokens that are not revoked, newest first (expired ones included)."""
        authorize(principal, Action.MANAGE_TOKENS)
        return self._store.tokens_of(principal.user_id, limit=_TOKEN_LIST_LIMIT)

    def create_token(
        self,
        principal: Principal,
        *,
        name: str,
        scopes: frozenset[Scope],
        expires_in_days: int,
    ) -> IssuedToken:
        """Issue a token for the caller; the secret is returned here and never again."""
        authorize(principal, Action.MANAGE_TOKENS)
        now = self._clock.now()
        if self._store.count_live_tokens(principal.user_id, now=now) >= ACCESS_TOKEN_MAX_PER_USER:
            raise AccessTokenLimitError
        secret, token = new_access_token(
            principal.user_id,
            name=name,
            scopes=scopes,
            expires_in_days=expires_in_days,
            now=now,
            new_id=self._new_id,
        )
        self._store.add_token(token)
        logger.info("access token created (user %s, token %s)", principal.user_id, token.id)
        return IssuedToken(secret=secret, token=token)

    def revoke_token(self, principal: Principal, token_id: UUID) -> None:
        """Revoke one of the caller's tokens; another user's token is reported as missing."""
        authorize(principal, Action.MANAGE_TOKENS)
        if not self._store.revoke_token(principal.user_id, token_id, now=self._clock.now()):
            raise AccessTokenNotFoundError
        logger.info("access token revoked (user %s, token %s)", principal.user_id, token_id)


def _blocking_oldest(counts: FailureCounts) -> datetime | None:
    """The oldest failure of whichever limit is reached (it frees a slot first), else None."""
    blocking = [
        oldest
        for count, limit, oldest in (
            (counts.account, SIGN_IN_MAX_FAILURES_PER_ACCOUNT, counts.oldest_account),
            (counts.ip, SIGN_IN_MAX_FAILURES_PER_IP, counts.oldest_ip),
        )
        if count >= limit and oldest is not None
    ]
    return max(blocking) if blocking else None
