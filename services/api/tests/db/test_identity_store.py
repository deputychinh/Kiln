from datetime import UTC, datetime, timedelta

import pytest
from db_fixtures import insert_token, insert_user
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from kiln_api.domain.identity import SESSION_IDLE, User, new_session
from kiln_api.domain.ids import uuid7
from kiln_api.enums import Scope
from kiln_api.errors import EmailTakenError
from kiln_api.ports import FailureCounts
from kiln_api.repositories.identity import SqlIdentityStore

T0 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
IP = "203.0.113.7"
LIMITS = (10, 50)


def test_an_email_can_belong_to_one_user_only(engine: Engine, user: User) -> None:
    with pytest.raises(EmailTakenError):
        insert_user(engine, email=user.email)


def test_the_database_refuses_an_upper_case_email_or_a_non_argon2id_hash(engine: Engine) -> None:
    for column, value in (("email", "Ada@Kiln.test"), ("password_hash", "$2b$12$bcrypt")):
        values = {"email": "x@kiln.test", "password_hash": "$argon2id$v=19$x", column: value}
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text("INSERT INTO users VALUES (:id, :email, 'X', :password_hash, now(), now())"),
                {"id": uuid7(), **values},
            )


def test_the_database_refuses_an_unknown_scope(engine: Engine, user: User) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO access_tokens (id, user_id, name, prefix, token_hash, scopes,"
                " created_at, expires_at) VALUES (:id, :user, 'x', 'kiln_pat_x', :hash,"
                " ARRAY['read', 'admin'], now(), now() + interval '1 day')"
            ),
            {"id": uuid7(), "user": user.id, "hash": b"\1" * 32},
        )


def test_dead_sessions_are_purged_and_live_ones_kept(engine: Engine, user: User) -> None:
    store = SqlIdentityStore(engine)
    _, idle = new_session(user.id, now=T0 - SESSION_IDLE)
    _, old = new_session(user.id, now=T0 - timedelta(hours=8))
    live_raw, live = new_session(user.id, now=T0)
    for session in (idle, old, live):
        store.add_session(session)

    purged = store.purge_sessions(now=T0, idle=SESSION_IDLE)

    assert purged == 2
    assert store.session_user(live.id_hash) is not None
    assert store.session_user(idle.id_hash) is None
    assert live_raw  # the raw id is never stored


def test_touching_a_session_never_moves_it_back(engine: Engine, user: User) -> None:
    store = SqlIdentityStore(engine)
    _, session = new_session(user.id, now=T0)
    store.add_session(session)

    store.touch_session(session.id_hash, now=T0 + timedelta(minutes=5))
    store.touch_session(session.id_hash, now=T0 + timedelta(minutes=1))

    found = store.session_user(session.id_hash)
    assert found is not None
    assert found[0].last_seen_at == T0 + timedelta(minutes=5)


def test_attempts_are_counted_per_account_and_per_address_inside_the_window(
    engine: Engine,
) -> None:
    store = SqlIdentityStore(engine)
    ada, bob = b"a" * 32, b"b" * 32
    for key, ip, at in (
        (ada, IP, T0 - timedelta(minutes=20)),  # outside the window: pruned on the next insert
        (ada, IP, T0 - timedelta(minutes=10)),
        (ada, "198.51.100.1", T0 - timedelta(minutes=5)),
        (bob, IP, T0 - timedelta(minutes=1)),
    ):
        store.reserve_attempt(
            attempt_id=uuid7(),
            account_key=key,
            client_ip=ip,
            now=at,
            since=at - timedelta(minutes=15),
            limits=LIMITS,
        )

    counts = store.failures_since(account_key=ada, client_ip=IP, since=T0 - timedelta(minutes=15))

    assert (counts.account, counts.ip) == (2, 2)
    assert counts.oldest_account == T0 - timedelta(minutes=10)
    assert counts.oldest_ip == T0 - timedelta(minutes=10)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM sign_in_failures")).scalar() == 3


def test_clearing_failures_touches_only_that_account(engine: Engine) -> None:
    store = SqlIdentityStore(engine)
    for key in (b"a" * 32, b"b" * 32):
        store.reserve_attempt(
            attempt_id=uuid7(),
            account_key=key,
            client_ip=IP,
            now=T0,
            since=T0 - timedelta(minutes=15),
            limits=LIMITS,
        )

    store.clear_failures(b"a" * 32)

    counts = store.failures_since(account_key=b"b" * 32, client_ip=IP, since=T0 - timedelta(1))
    assert (counts.account, counts.ip) == (1, 1)


def test_the_list_shows_expired_tokens_but_not_revoked_ones_newest_first(
    engine: Engine, user: User
) -> None:
    store = SqlIdentityStore(engine)
    insert_token(engine, user, now=T0 - timedelta(days=30), expires_in_days=7)  # expired
    insert_token(engine, user, now=T0, scopes=frozenset({Scope.READ}))
    revoked = store.tokens_of(user.id, limit=10)[0]
    insert_token(engine, user, now=T0 + timedelta(seconds=1))
    assert store.revoke_token(user.id, revoked.id, now=T0)

    listed = store.tokens_of(user.id, limit=10)

    assert [t.created_at for t in listed] == [T0 + timedelta(seconds=1), T0 - timedelta(days=30)]
    assert store.count_live_tokens(user.id, now=T0) == 1


def test_revoking_is_scoped_to_the_owner(engine: Engine, user: User) -> None:
    store = SqlIdentityStore(engine)
    insert_token(engine, user, now=T0)
    token = store.tokens_of(user.id, limit=1)[0]
    bob = insert_user(engine, email="bob@kiln.test")

    assert not store.revoke_token(bob.id, token.id, now=T0)
    assert store.revoke_token(user.id, token.id, now=T0)
    assert not store.revoke_token(user.id, token.id, now=T0)  # already revoked


def test_a_user_can_be_found_by_email_and_get_a_new_hash(engine: Engine, user: User) -> None:
    store = SqlIdentityStore(engine)

    store.set_password_hash(user.id, "$argon2id$v=19$new", now=T0)

    found = store.user_by_email("ada@kiln.test")
    assert found is not None
    assert (found.password_hash, found.updated_at) == ("$argon2id$v=19$new", T0)
    assert store.user_by_email("nobody@kiln.test") is None


def test_an_attempt_past_a_limit_is_refused_and_not_recorded(engine: Engine) -> None:
    store = SqlIdentityStore(engine)

    def reserve() -> FailureCounts | None:
        return store.reserve_attempt(
            attempt_id=uuid7(),
            account_key=b"a" * 32,
            client_ip=IP,
            now=T0,
            since=T0 - timedelta(minutes=15),
            limits=(2, 50),
        )

    first, second, third = reserve(), reserve(), reserve()

    assert (first, second) == (None, None)
    assert third is not None
    assert (third.account, third.oldest_account) == (2, T0)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM sign_in_failures")).scalar() == 2
