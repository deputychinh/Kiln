"""Sign-in, sign-out, sessions and the CSRF check (KILN-12)."""

from collections.abc import Iterator
from http.cookies import SimpleCookie

import pytest
from db_fixtures import APP_HEADERS, TEST_HASHER, TEST_PASSWORD, insert_user
from fakes import FakeStorage, FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from kiln_api.config import Settings
from kiln_api.container import build_container
from kiln_api.db.schema import sessions
from kiln_api.domain.identity import User
from kiln_api.domain.ids import uuid7
from kiln_api.enums import Environment
from kiln_api.main import create_app
from kiln_api.repositories.identity import SqlIdentityStore
from kiln_api.services.identity import IdentityService

SIGN_IN = "/api/v1/sessions"
SIGN_OUT = "/api/v1/sessions/current"
ROCK = {"name": "Rock", "file_name": "rock.png", "content_type": "image/png", "size_bytes": 10}


def _sign_in(client: TestClient, email: str = "ada@kiln.test", password: str = TEST_PASSWORD):  # type: ignore[no-untyped-def]
    return client.post(SIGN_IN, json={"email": email, "password": password})


def _set_cookie(response) -> SimpleCookie:  # type: ignore[no-untyped-def]
    cookie: SimpleCookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie


def _session_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(sessions)).scalar_one())


def test_signing_in_sets_an_httponly_lax_session_cookie_and_returns_the_user(
    anonymous_client: TestClient, user: User
) -> None:
    response = _sign_in(anonymous_client, email="  ADA@kiln.test ")

    assert response.status_code == 201
    assert response.headers["Location"] == "/api/v1/sessions/current"
    assert response.json() == {
        "id": str(user.id),
        "email": "ada@kiln.test",
        "display_name": "Ada Artist",
        "auth_method": "session",
        "scopes": ["read", "write"],
    }
    morsel = _set_cookie(response)["kiln_session"]
    assert morsel["httponly"] is True
    assert morsel["samesite"] == "lax"
    assert morsel["path"] == "/"
    assert morsel["max-age"] == "28800"
    assert not morsel["secure"]  # local http: a Secure cookie would be dropped
    assert "domain" not in {k for k, v in morsel.items() if v}
    assert response.headers["Cache-Control"] == "no-store"


def test_the_session_cookie_is_secure_with_the_host_prefix_over_https(
    database_url: str, engine: Engine
) -> None:
    insert_user(engine)
    settings = Settings(env=Environment.PRODUCTION, database_url=database_url)
    container = build_container(
        settings, engine=engine, storage=FakeStorage(), clock=FixedClock(), hasher=TEST_HASHER
    )
    with TestClient(
        create_app(settings, container=container),
        headers=APP_HEADERS,
        base_url="https://testserver",
    ) as client:
        response = _sign_in(client)
        me = client.get("/api/v1/me")

    morsel = _set_cookie(response)["__Host-kiln_session"]
    assert morsel["secure"] is True
    assert morsel["path"] == "/"
    assert me.status_code == 200


def test_the_signed_in_session_reaches_assets(anonymous_client: TestClient, user: User) -> None:
    _sign_in(anonymous_client)

    created = anonymous_client.post("/api/v1/assets", json=ROCK)

    assert created.status_code == 201
    assert created.json()["asset"]["owner_id"] == str(user.id)
    assert anonymous_client.get("/api/v1/assets").status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("ada@kiln.test", "wrong password!"),
        ("nobody@kiln.test", TEST_PASSWORD),
        ("not an email", TEST_PASSWORD),
    ],
)
@pytest.mark.usefixtures("user")
def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(
    anonymous_client: TestClient, email: str, password: str
) -> None:
    response = _sign_in(anonymous_client, email, password)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="kiln"'
    body = response.json()
    assert (body["code"], body["detail"]) == (
        "INVALID_CREDENTIALS",
        "The email or password is not correct.",
    )
    assert "set-cookie" not in response.headers


class _CountingHasher:
    def __init__(self) -> None:
        self.verified: list[str] = []

    def hash(self, password: str) -> str:
        return TEST_HASHER.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        self.verified.append(password_hash)
        return TEST_HASHER.verify(password_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        return TEST_HASHER.needs_rehash(password_hash)


@pytest.fixture
def counting() -> _CountingHasher:
    return _CountingHasher()


@pytest.fixture
def counted_client(
    database_url: str, engine: Engine, counting: _CountingHasher
) -> Iterator[TestClient]:
    settings = Settings(env=Environment.TEST, database_url=database_url)
    container = build_container(
        settings, engine=engine, storage=FakeStorage(), clock=FixedClock(), hasher=counting
    )
    with TestClient(create_app(settings, container=container), headers=APP_HEADERS) as client:
        yield client


@pytest.mark.parametrize("email", ["nobody@kiln.test", "not an email", "ada@kiln.test"])
def test_every_failed_sign_in_does_one_argon2_verification(
    counted_client: TestClient, counting: _CountingHasher, engine: Engine, email: str
) -> None:
    """Unknown accounts cost the same hash work as real ones, so timing tells nothing."""
    insert_user(engine)

    _sign_in(counted_client, email, "wrong password!")

    assert len(counting.verified) == 1
    assert counting.verified[0].startswith("$argon2id$")


@pytest.mark.usefixtures("user")
def test_a_stored_hash_with_old_parameters_is_upgraded_at_sign_in(
    database_url: str, engine: Engine
) -> None:
    settings = Settings(env=Environment.TEST, database_url=database_url)
    container = build_container(settings, engine=engine, storage=FakeStorage(), clock=FixedClock())
    with TestClient(create_app(settings, container=container), headers=APP_HEADERS) as client:
        assert _sign_in(client).status_code == 201
        stored = container.identity._store.user_by_email("ada@kiln.test")

    assert stored is not None
    assert stored.password_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")


@pytest.mark.usefixtures("user")
def test_signing_in_again_replaces_the_old_session(
    anonymous_client: TestClient, engine: Engine
) -> None:
    _sign_in(anonymous_client)
    old = anonymous_client.cookies["kiln_session"]

    _sign_in(anonymous_client)
    new = anonymous_client.cookies["kiln_session"]

    assert new != old
    assert _session_count(engine) == 1
    anonymous_client.cookies.clear()
    anonymous_client.cookies.set("kiln_session", old)
    assert anonymous_client.get("/api/v1/me").status_code == 401


@pytest.mark.usefixtures("user")
def test_signing_out_ends_the_session_and_clears_the_cookie(
    anonymous_client: TestClient, engine: Engine
) -> None:
    _sign_in(anonymous_client)
    old = anonymous_client.cookies["kiln_session"]

    response = anonymous_client.delete(SIGN_OUT)

    assert response.status_code == 204
    assert 'kiln_session=""' in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert _session_count(engine) == 0
    anonymous_client.cookies.clear()
    anonymous_client.cookies.set("kiln_session", old)
    assert anonymous_client.get("/api/v1/me").status_code == 401


def test_signing_out_without_a_session_still_succeeds(anonymous_client: TestClient) -> None:
    assert anonymous_client.delete(SIGN_OUT).status_code == 204


def test_an_unknown_or_oversized_session_cookie_is_refused(anonymous_client: TestClient) -> None:
    for value in ("not-a-session", "x" * 5000):
        anonymous_client.cookies.set("kiln_session", value)

        response = anonymous_client.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"


def test_a_session_idle_for_30_minutes_is_signed_out(
    session_client: TestClient, clock: FixedClock
) -> None:
    clock.advance(29 * 60)
    assert session_client.get("/api/v1/me").status_code == 200  # activity moves the idle bound

    clock.advance(29 * 60)
    assert session_client.get("/api/v1/me").status_code == 200

    clock.advance(30 * 60)
    assert session_client.get("/api/v1/me").status_code == 401


def test_a_session_ends_after_8_hours_even_when_used(
    session_client: TestClient, clock: FixedClock
) -> None:
    for _ in range(16):
        clock.advance(29 * 60)
        assert session_client.get("/api/v1/me").status_code == 200

    clock.advance(16 * 60)  # 8 h after sign-in
    assert session_client.get("/api/v1/me").status_code == 401


# --- CSRF --------------------------------------------------------------------------------------


def test_a_cookie_write_without_the_csrf_header_is_refused(
    session_client: TestClient, engine: Engine
) -> None:
    del session_client.headers["X-Kiln-Csrf"]

    response = session_client.post("/api/v1/assets", json=ROCK)

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM assets").scalar_one() == 0


def test_a_cookie_write_from_another_origin_is_refused(session_client: TestClient) -> None:
    session_client.headers["Origin"] = "https://evil.example"

    response = session_client.post("/api/v1/assets", json=ROCK)

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"


def test_a_cookie_write_without_origin_needs_same_origin_fetch_metadata(
    session_client: TestClient,
) -> None:
    del session_client.headers["Origin"]

    refused = session_client.post("/api/v1/assets", json=ROCK)
    cross_site = session_client.post(
        "/api/v1/assets", json=ROCK, headers={"Sec-Fetch-Site": "cross-site"}
    )
    same_origin = session_client.post(
        "/api/v1/assets", json=ROCK, headers={"Sec-Fetch-Site": "same-origin"}
    )

    assert (refused.status_code, cross_site.status_code, same_origin.status_code) == (
        403,
        403,
        201,
    )


def test_cookie_reads_need_no_csrf_header(session_client: TestClient) -> None:
    del session_client.headers["X-Kiln-Csrf"]
    session_client.headers["Origin"] = "https://evil.example"

    assert session_client.get("/api/v1/assets").status_code == 200


def test_a_token_write_needs_no_csrf_header(client: TestClient) -> None:
    del client.headers["X-Kiln-Csrf"]
    del client.headers["Origin"]

    assert client.post("/api/v1/assets", json=ROCK).status_code == 201


@pytest.mark.parametrize(
    "headers",
    [{"X-Kiln-Csrf": ""}, {"Origin": "https://evil.example"}, {"Origin": "null"}],
)
@pytest.mark.usefixtures("user")
def test_sign_in_and_sign_out_also_check_the_origin_against_login_csrf(
    anonymous_client: TestClient, headers: dict[str, str]
) -> None:
    anonymous_client.headers.update(headers)

    assert _sign_in(anonymous_client).status_code == 403
    assert anonymous_client.delete(SIGN_OUT).status_code == 403


def test_a_cross_origin_preflight_with_the_csrf_header_is_refused(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.options(
        "/api/v1/assets",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-kiln-csrf,content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


# --- throttling --------------------------------------------------------------------------------


@pytest.mark.usefixtures("user")
def test_ten_failures_lock_the_account_for_15_minutes_even_with_the_right_password(
    anonymous_client: TestClient, clock: FixedClock
) -> None:
    for _ in range(10):
        assert _sign_in(anonymous_client, password="wrong password!").status_code == 401

    locked = _sign_in(anonymous_client)

    assert locked.status_code == 429
    assert locked.json()["code"] == "SIGN_IN_THROTTLED"
    assert locked.headers["Retry-After"] == "900"
    assert "set-cookie" not in locked.headers
    clock.advance(10 * 60)
    assert _sign_in(anonymous_client).headers["Retry-After"] == "300"
    clock.advance(5 * 60)
    assert _sign_in(anonymous_client).status_code == 201


@pytest.mark.usefixtures("user")
def test_an_unknown_account_is_throttled_exactly_like_a_real_one(
    anonymous_client: TestClient,
) -> None:
    answers = []
    for email in ("ada@kiln.test", "nobody@kiln.test"):
        for _ in range(10):
            _sign_in(anonymous_client, email, "wrong password!")
        locked = _sign_in(anonymous_client, email, "wrong password!")
        answers.append((locked.status_code, locked.json()["detail"], locked.headers["Retry-After"]))

    assert answers[0] == answers[1]
    assert answers[0][0] == 429


@pytest.mark.usefixtures("user")
def test_a_successful_sign_in_forgets_the_accounts_earlier_failures(
    anonymous_client: TestClient,
) -> None:
    for _ in range(9):
        _sign_in(anonymous_client, password="wrong password!")
    assert _sign_in(anonymous_client).status_code == 201

    for _ in range(9):
        assert _sign_in(anonymous_client, password="wrong password!").status_code == 401
    assert _sign_in(anonymous_client).status_code == 201


@pytest.mark.usefixtures("user")
def test_fifty_failures_from_one_address_block_it_for_every_account(
    anonymous_client: TestClient,
) -> None:
    for number in range(50):
        _sign_in(anonymous_client, f"guess{number}@kiln.test", "wrong password!")

    response = _sign_in(anonymous_client)

    assert response.status_code == 429
    assert response.json()["code"] == "SIGN_IN_THROTTLED"


@pytest.mark.parametrize(
    ("created_with", "signed_in_with"),
    [
        ("cafe\u0301 au lait 42", "caf\u00e9 au lait 42"),
        ("caf\u00e9 au lait 42", "cafe\u0301 au lait 42"),
    ],
)
def test_a_password_signs_in_whichever_unicode_form_the_keyboard_sent(
    anonymous_client: TestClient, engine: Engine, created_with: str, signed_in_with: str
) -> None:
    identity = IdentityService(SqlIdentityStore(engine), TEST_HASHER, FixedClock(), uuid7)
    identity.create_user("zoe@kiln.test", "Zoe", created_with)

    assert _sign_in(anonymous_client, "zoe@kiln.test", signed_in_with).status_code == 201
