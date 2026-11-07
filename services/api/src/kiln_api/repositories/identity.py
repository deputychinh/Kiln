"""Postgres adapter for the `IdentityStore` port (KILN-12)."""

import hashlib
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, Row, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from kiln_api.constants import SIGN_IN_WINDOW_MINUTES
from kiln_api.db.schema import access_tokens, sessions, sign_in_failures, users
from kiln_api.domain.identity import AccessToken, Session, User
from kiln_api.enums import Scope
from kiln_api.errors import EmailTakenError
from kiln_api.ports import FailureCounts

_WINDOW = timedelta(minutes=SIGN_IN_WINDOW_MINUTES)


def _user(row: Row[Any]) -> User:
    return User(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        password_hash=row.password_hash,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _session(row: Row[Any]) -> Session:
    return Session(
        id_hash=row.id_hash,
        user_id=row.user_id,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
    )


def _token(row: Row[Any]) -> AccessToken:
    return AccessToken(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        prefix=row.prefix,
        token_hash=row.token_hash,
        scopes=frozenset(Scope(scope) for scope in row.scopes),
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


def _lock_id(name: bytes) -> int:
    """A signed 64-bit advisory-lock key from a name (account key or address)."""
    return int.from_bytes(hashlib.sha256(name).digest()[:8], "big", signed=True)


def _failure_counts(
    connection: Connection, account_key: bytes, client_ip: str, since: datetime
) -> FailureCounts:
    """Failures after `since` for the account and for the IP: two index ranges, one statement."""
    recent = sign_in_failures.c.created_at > since
    by_account = (sign_in_failures.c.account_key == account_key) & recent
    by_ip = (sign_in_failures.c.client_ip == client_ip) & recent
    query = select(
        func.count().filter(by_account),
        func.count().filter(by_ip),
        func.min(sign_in_failures.c.created_at).filter(by_account),
        func.min(sign_in_failures.c.created_at).filter(by_ip),
    ).where(
        recent,
        or_(
            sign_in_failures.c.account_key == account_key,
            sign_in_failures.c.client_ip == client_ip,
        ),
    )
    account, ip, oldest_account, oldest_ip = connection.execute(query).one()
    return FailureCounts(account=account, ip=ip, oldest_account=oldest_account, oldest_ip=oldest_ip)


def _user_columns() -> list[Any]:
    return [column.label(f"u_{column.name}") for column in users.c]


def _prefixed_user(row: Row[Any]) -> User:
    return User(
        id=row.u_id,
        email=row.u_email,
        display_name=row.u_display_name,
        password_hash=row.u_password_hash,
        created_at=row.u_created_at,
        updated_at=row.u_updated_at,
    )


class SqlIdentityStore:
    """Each method is its own short transaction."""

    def __init__(self, engine: Engine) -> None:
        """Use `engine` for every statement."""
        self._engine = engine

    def add_user(self, user: User) -> None:
        """Insert a user; the unique email constraint decides races."""
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(users).values(
                        id=user.id,
                        email=user.email,
                        display_name=user.display_name,
                        password_hash=user.password_hash,
                        created_at=user.created_at,
                        updated_at=user.updated_at,
                    )
                )
        except IntegrityError as error:
            raise EmailTakenError from error

    def user_by_email(self, email: str) -> User | None:
        """Look a user up by normalised email."""
        with self._engine.connect() as connection:
            row = connection.execute(select(users).where(users.c.email == email)).one_or_none()
        return None if row is None else _user(row)

    def set_password_hash(self, user_id: UUID, password_hash: str, *, now: datetime) -> None:
        """Replace the stored hash."""
        with self._engine.begin() as connection:
            connection.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(password_hash=password_hash, updated_at=now)
            )

    def add_session(self, session: Session) -> None:
        """Insert a session."""
        with self._engine.begin() as connection:
            connection.execute(
                insert(sessions).values(
                    id_hash=session.id_hash,
                    user_id=session.user_id,
                    created_at=session.created_at,
                    last_seen_at=session.last_seen_at,
                    expires_at=session.expires_at,
                )
            )

    def session_user(self, id_hash: bytes) -> tuple[Session, User] | None:
        """Session and user by the primary key, one join."""
        query = (
            select(sessions, *_user_columns())
            .join(users, users.c.id == sessions.c.user_id)
            .where(sessions.c.id_hash == id_hash)
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).one_or_none()
        return None if row is None else (_session(row), _prefixed_user(row))

    def touch_session(self, id_hash: bytes, *, now: datetime) -> None:
        """Move `last_seen_at` forward (never back)."""
        with self._engine.begin() as connection:
            connection.execute(
                update(sessions)
                .where(sessions.c.id_hash == id_hash)
                .values(last_seen_at=func.greatest(sessions.c.last_seen_at, now))
            )

    def delete_session(self, id_hash: bytes) -> None:
        """Delete by id hash."""
        with self._engine.begin() as connection:
            connection.execute(delete(sessions).where(sessions.c.id_hash == id_hash))

    def purge_sessions(self, *, now: datetime, idle: timedelta) -> int:
        """Delete dead sessions; called on each sign-in, so the table stays small."""
        with self._engine.begin() as connection:
            result = connection.execute(
                delete(sessions).where(
                    or_(sessions.c.expires_at <= now, sessions.c.last_seen_at <= now - idle)
                )
            )
        return result.rowcount

    def add_token(self, token: AccessToken) -> None:
        """Insert a token (its hash, never the token)."""
        with self._engine.begin() as connection:
            connection.execute(
                insert(access_tokens).values(
                    id=token.id,
                    user_id=token.user_id,
                    name=token.name,
                    prefix=token.prefix,
                    token_hash=token.token_hash,
                    scopes=sorted(scope.value for scope in token.scopes),
                    created_at=token.created_at,
                    expires_at=token.expires_at,
                )
            )

    def token_user(self, token_hash: bytes) -> tuple[AccessToken, User] | None:
        """Token and user by the unique hash, one join."""
        query = (
            select(access_tokens, *_user_columns())
            .join(users, users.c.id == access_tokens.c.user_id)
            .where(access_tokens.c.token_hash == token_hash)
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).one_or_none()
        return None if row is None else (_token(row), _prefixed_user(row))

    def tokens_of(self, user_id: UUID, *, limit: int) -> list[AccessToken]:
        """Not revoked, newest first (index on user_id, created_at)."""
        query = (
            select(access_tokens)
            .where(access_tokens.c.user_id == user_id, access_tokens.c.revoked_at.is_(None))
            .order_by(access_tokens.c.created_at.desc(), access_tokens.c.id.desc())
            .limit(limit)
        )
        with self._engine.connect() as connection:
            return [_token(row) for row in connection.execute(query).all()]

    def count_live_tokens(self, user_id: UUID, *, now: datetime) -> int:
        """Neither revoked nor expired."""
        query = select(func.count()).where(
            access_tokens.c.user_id == user_id,
            access_tokens.c.revoked_at.is_(None),
            access_tokens.c.expires_at > now,
        )
        with self._engine.connect() as connection:
            return int(connection.execute(query).scalar_one())

    def revoke_token(self, user_id: UUID, token_id: UUID, *, now: datetime) -> bool:
        """Owner-scoped: another user's id updates nothing."""
        with self._engine.begin() as connection:
            result = connection.execute(
                update(access_tokens)
                .where(
                    access_tokens.c.id == token_id,
                    access_tokens.c.user_id == user_id,
                    access_tokens.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
        return result.rowcount == 1

    def touch_token(self, token_id: UUID, *, now: datetime) -> None:
        """Move `last_used_at` forward (never back)."""
        with self._engine.begin() as connection:
            connection.execute(
                update(access_tokens)
                .where(access_tokens.c.id == token_id)
                .values(
                    last_used_at=func.greatest(
                        func.coalesce(access_tokens.c.last_used_at, now), now
                    )
                )
            )

    def reserve_attempt(  # noqa: PLR0913 - keyword-only facts of one attempt
        self,
        *,
        attempt_id: UUID,
        account_key: bytes,
        client_ip: str,
        now: datetime,
        since: datetime,
        limits: tuple[int, int],
    ) -> FailureCounts | None:
        """Lock the account, then the IP (always that order: no deadlock), count, then insert.

        Transaction-scoped advisory locks end at commit; the password check runs after it, so a
        lock is held for three short statements, never for Argon2id.
        """
        max_account, max_ip = limits
        with self._engine.begin() as connection:
            for lock in (
                _lock_id(b"account:" + account_key),
                _lock_id(b"ip:" + client_ip.encode()),
            ):
                connection.execute(select(func.pg_advisory_xact_lock(lock)))
            connection.execute(
                delete(sign_in_failures).where(sign_in_failures.c.created_at <= now - _WINDOW)
            )
            counts = _failure_counts(connection, account_key, client_ip, since)
            if counts.account >= max_account or counts.ip >= max_ip:
                return counts
            connection.execute(
                insert(sign_in_failures).values(
                    id=attempt_id, account_key=account_key, client_ip=client_ip, created_at=now
                )
            )
        return None

    def failures_since(
        self, *, account_key: bytes, client_ip: str, since: datetime
    ) -> FailureCounts:
        """Two index range counts in one round trip."""
        with self._engine.connect() as connection:
            return _failure_counts(connection, account_key, client_ip, since)

    def clear_failures(self, account_key: bytes) -> None:
        """Delete an account's failures."""
        with self._engine.begin() as connection:
            connection.execute(
                delete(sign_in_failures).where(sign_in_failures.c.account_key == account_key)
            )
