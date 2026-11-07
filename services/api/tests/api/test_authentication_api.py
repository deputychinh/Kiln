"""Every endpoint needs a principal; assets record who made them (KILN-12)."""

import pytest
from db_fixtures import insert_token, insert_user
from fakes import FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from kiln_api.domain.identity import User

PUBLIC = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/ready"),
    ("POST", "/api/v1/sessions"),  # signing in
    ("DELETE", "/api/v1/sessions/current"),  # signing out is safe without a session
}
SAMPLE_ID = "0190f1c2-0000-7000-8000-000000000001"
ROCK = {"name": "Rock", "file_name": "rock.png", "content_type": "image/png", "size_bytes": 10}


def _routes(client: TestClient) -> list[tuple[str, str]]:
    """Every operation the app serves, from its own OpenAPI document."""
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    return sorted((method.upper(), path) for path, item in paths.items() for method in item)


def test_every_route_needs_a_principal_except_health_and_sign_in(
    anonymous_client: TestClient,
) -> None:
    protected = [r for r in _routes(anonymous_client) if r not in PUBLIC]
    assert len(protected) >= 9  # the asset, me and token routes

    answers = {
        (method, path): anonymous_client.request(
            method,
            path.replace("{asset_id}", SAMPLE_ID)
            .replace("{version_id}", SAMPLE_ID)
            .replace("{token_id}", SAMPLE_ID),
            json={},
        )
        for method, path in protected
    }

    assert {k: v.status_code for k, v in answers.items()} == dict.fromkeys(answers, 401)
    assert all(v.headers["WWW-Authenticate"] == 'Bearer realm="kiln"' for v in answers.values())
    assert {r for r in _routes(anonymous_client) if r in PUBLIC} == PUBLIC


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_stays_public(anonymous_client: TestClient, path: str) -> None:
    assert anonymous_client.get(path).status_code == 200


def test_an_asset_records_its_owner_and_each_version_its_uploader(
    client: TestClient, anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    created = client.post("/api/v1/assets", json=ROCK).json()
    bob = insert_user(engine, email="bob@kiln.test", display_name="Bob")
    as_bob = {"Authorization": f"Bearer {insert_token(engine, bob, now=clock.now())}"}

    second = anonymous_client.post(
        f"/api/v1/assets/{created['asset']['id']}/versions",
        json={k: v for k, v in ROCK.items() if k != "name"},
        headers=as_bob,
    )

    assert created["asset"]["owner_id"] == str(user.id)
    assert created["version"]["uploaded_by"] == str(user.id)
    assert second.status_code == 201
    assert second.json()["version"]["uploaded_by"] == str(bob.id)
    detail = anonymous_client.get(f"/api/v1/assets/{created['asset']['id']}", headers=as_bob)
    assert detail.json()["owner_id"] == str(user.id)  # single workspace: Bob sees Ada's asset


def test_an_idempotency_key_belongs_to_the_user_who_sent_it(
    client: TestClient, anonymous_client: TestClient, engine: Engine, clock: FixedClock
) -> None:
    bob = insert_user(engine, email="bob@kiln.test", display_name="Bob")
    as_bob = {"Authorization": f"Bearer {insert_token(engine, bob, now=clock.now())}"}
    key = {"Idempotency-Key": '"same-key"'}

    first = client.post("/api/v1/assets", json=ROCK, headers=key)
    other = anonymous_client.post("/api/v1/assets", json=ROCK, headers={**key, **as_bob})

    assert (first.status_code, other.status_code) == (201, 201)
    assert first.json()["asset"]["id"] != other.json()["asset"]["id"]
    assert "Idempotent-Replayed" not in other.headers


def test_api_answers_are_never_cached(client: TestClient) -> None:
    assert client.get("/api/v1/assets").headers["Cache-Control"] == "no-store"
