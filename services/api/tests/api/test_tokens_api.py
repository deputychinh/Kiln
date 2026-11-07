"""Personal access tokens: issue, use, scope, expire, revoke (KILN-12)."""

from typing import Any

import pytest
from db_fixtures import insert_token, insert_user
from fakes import FakeStorage, FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from kiln_api.domain.identity import User
from kiln_api.enums import Scope

TOKENS = "/api/v1/me/tokens"
ROCK = {"name": "Rock", "file_name": "rock.png", "content_type": "image/png", "size_bytes": 10}
CLI = {"name": "Blender laptop", "scopes": ["read", "write"], "expires_in_days": 90}


def _create(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post(TOKENS, json={**CLI, **changes})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def test_a_new_token_is_shown_once_and_listed_without_its_secret(
    session_client: TestClient,
) -> None:
    response = session_client.post(TOKENS, json=CLI)

    assert response.status_code == 201
    created = response.json()
    assert response.headers["Location"] == f"{TOKENS}/{created['id']}"
    assert created["token"].startswith("kiln_pat_")
    assert created["prefix"] == created["token"][:15]
    assert created["scopes"] == ["read", "write"]
    assert created["expires_at"].startswith("2027-02-02")  # 90 days after 2026-11-04
    listed = session_client.get(TOKENS).json()["items"]
    assert [item["id"] for item in listed] == [created["id"]]
    assert "token" not in listed[0]
    assert created["token"] not in session_client.get(TOKENS).text


def test_a_token_authenticates_as_its_user_and_records_when_it_was_used(
    session_client: TestClient, anonymous_client: TestClient, user: User, clock: FixedClock
) -> None:
    secret = _create(session_client, scopes=["read"])["token"]
    clock.advance(60)

    me = anonymous_client.get("/api/v1/me", headers=_bearer(secret))

    assert me.status_code == 200
    assert me.json()["auth_method"] == "token"
    assert me.json()["scopes"] == ["read"]
    assert me.json()["id"] == str(user.id)
    assert session_client.get(TOKENS).json()["items"][0]["last_used_at"] is not None


def test_a_read_token_cannot_write_assets_bola(
    anonymous_client: TestClient,
    engine: Engine,
    user: User,
    clock: FixedClock,
    storage: FakeStorage,
) -> None:
    """Broken object/function level authorization: each write refuses a read-only token."""
    writer = _bearer(insert_token(engine, user, now=clock.now()))
    reader = _bearer(insert_token(engine, user, now=clock.now(), scopes=frozenset({Scope.READ})))
    created = anonymous_client.post("/api/v1/assets", json=ROCK, headers=writer).json()
    asset_id, version_id = created["asset"]["id"], created["version"]["id"]

    attempts = [
        anonymous_client.post("/api/v1/assets", json=ROCK, headers=reader),
        anonymous_client.post(
            f"/api/v1/assets/{asset_id}/versions",
            json={k: v for k, v in ROCK.items() if k != "name"},
            headers=reader,
        ),
        anonymous_client.post(f"/api/v1/asset-versions/{version_id}/completions", headers=reader),
    ]

    assert [(r.status_code, r.json()["code"]) for r in attempts] == [
        (403, "INSUFFICIENT_SCOPE")
    ] * 3
    assert anonymous_client.get(f"/api/v1/assets/{asset_id}", headers=reader).status_code == 200
    assert storage.signed[1:] == []  # nothing signed for the refused writes


def test_a_write_only_token_cannot_read(
    anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    writer = _bearer(insert_token(engine, user, now=clock.now(), scopes=frozenset({Scope.WRITE})))

    response = anonymous_client.get("/api/v1/assets", headers=writer)

    assert (response.status_code, response.json()["code"]) == (403, "INSUFFICIENT_SCOPE")


def test_a_token_cannot_list_create_or_revoke_tokens(client: TestClient) -> None:
    answers = [
        client.get(TOKENS),
        client.post(TOKENS, json=CLI),
        client.delete(f"{TOKENS}/0190f1c2-0000-7000-8000-000000000001"),
    ]

    assert {(r.status_code, r.json()["code"]) for r in answers} == {(403, "SESSION_REQUIRED")}


def test_a_revoked_token_stops_working_at_once(
    session_client: TestClient, anonymous_client: TestClient
) -> None:
    created = _create(session_client)
    assert anonymous_client.get("/api/v1/me", headers=_bearer(created["token"])).status_code == 200

    revoked = session_client.delete(f"{TOKENS}/{created['id']}")

    assert revoked.status_code == 204
    assert anonymous_client.get("/api/v1/me", headers=_bearer(created["token"])).status_code == 401
    assert session_client.get(TOKENS).json()["items"] == []
    again = session_client.delete(f"{TOKENS}/{created['id']}")
    assert (again.status_code, again.json()["code"]) == (404, "ACCESS_TOKEN_NOT_FOUND")


def test_another_users_token_cannot_be_seen_or_revoked(
    session_client: TestClient, anonymous_client: TestClient, engine: Engine, clock: FixedClock
) -> None:
    bob = insert_user(engine, email="bob@kiln.test", display_name="Bob")
    bobs_secret = insert_token(engine, bob, now=clock.now())
    bobs_id = anonymous_client.get("/api/v1/me", headers=_bearer(bobs_secret)).json()["id"]
    assert bobs_id == str(bob.id)
    bobs_token_id = (
        engine.connect()
        .exec_driver_sql("SELECT id FROM access_tokens WHERE user_id = %s", (bob.id,))
        .scalar_one()
    )

    response = session_client.delete(f"{TOKENS}/{bobs_token_id}")

    assert response.status_code == 404
    assert session_client.get(TOKENS).json()["items"] == []
    assert anonymous_client.get("/api/v1/me", headers=_bearer(bobs_secret)).status_code == 200


def test_an_expired_token_is_refused(
    session_client: TestClient, anonymous_client: TestClient, clock: FixedClock
) -> None:
    secret = _create(session_client, expires_in_days=7)["token"]
    clock.advance(7 * 24 * 3600 - 1)
    assert anonymous_client.get("/api/v1/me", headers=_bearer(secret)).status_code == 200

    clock.advance(1)

    assert anonymous_client.get("/api/v1/me", headers=_bearer(secret)).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"scopes": []},
        {"scopes": ["admin"]},
        {"expires_in_days": 1},
        {"expires_in_days": None},
        {"name": ""},
        {"extra": True},
    ],
)
def test_an_invalid_token_request_is_a_422(
    session_client: TestClient, changes: dict[str, Any]
) -> None:
    response = session_client.post(TOKENS, json={**CLI, **changes})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_a_token_name_with_hidden_characters_is_refused(session_client: TestClient) -> None:
    response = session_client.post(TOKENS, json={**CLI, "name": "CLI\u202e"})

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_TOKEN_NAME")


def test_a_user_holds_at_most_50_active_tokens(
    session_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    for _ in range(50):
        insert_token(engine, user, now=clock.now())

    response = session_client.post(TOKENS, json=CLI)

    assert (response.status_code, response.json()["code"]) == (409, "ACCESS_TOKEN_LIMIT")


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic YWRhOnB3",
        "Bearer",
        "Bearer   ",
        "Bearer kiln_pat_unknown",
        "Bearer kiln_pat_" + "a" * 43,
    ],
)
def test_a_malformed_or_unknown_bearer_is_refused(
    anonymous_client: TestClient, authorization: str
) -> None:
    response = anonymous_client.get("/api/v1/assets", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_a_bad_bearer_is_refused_even_next_to_a_valid_session(session_client: TestClient) -> None:
    response = session_client.get("/api/v1/me", headers={"Authorization": "Bearer nope"})

    assert response.status_code == 401
