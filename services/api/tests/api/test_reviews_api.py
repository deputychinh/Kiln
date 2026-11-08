"""Review states and history through the HTTP API (KILN-11)."""

import base64
from typing import Any
from uuid import UUID

import pytest
from db_fixtures import APP_HEADERS, insert_session, insert_token, insert_user
from fakes import FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text

from kiln_api.constants import CSRF_HEADER, SESSION_COOKIE_LOCAL
from kiln_api.db.schema import review_events
from kiln_api.domain.identity import User
from kiln_api.enums import Scope

ROCK = {
    "name": "Rock",
    "file_name": "T_Rock_01_BaseColor.png",
    "content_type": "image/png",
    "size_bytes": 2048,
}
APPROVE = {"action": "approve", "expected_state": "in_review"}
REQUEST = {"action": "request_changes", "expected_state": "in_review"}


def _version(client: TestClient, engine: Engine, *, status: str = "ready") -> str:
    created = client.post("/api/v1/assets", json=ROCK)
    assert created.status_code == 201, created.text
    version_id: str = created.json()["version"]["id"]
    _set_status(engine, version_id, status)
    return version_id


def _set_status(engine: Engine, version_id: str, status: str) -> None:
    reason = "UNREADABLE_IMAGE" if status == "failed" else None
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE asset_versions SET status = :s, failure_reason = :r WHERE id = :v"),
            {"s": status, "r": reason, "v": version_id},
        )


def _path(version_id: str) -> str:
    return f"/api/v1/asset-versions/{version_id}/review-transitions"


def _history(version_id: str) -> str:
    return f"/api/v1/asset-versions/{version_id}/review-history"


def _act(client: TestClient, version_id: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(_path(version_id), json=body)
    assert response.status_code == 201, response.text
    event: dict[str, Any] = response.json()
    return event


def _events(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(review_events)).scalar_one())


def _bearer(engine: Engine, user: User, clock: FixedClock, *scopes: Scope) -> dict[str, str]:
    token = insert_token(engine, user, now=clock.now(), scopes=frozenset(scopes or Scope))
    return {"Authorization": f"Bearer {token}"}


def _version_state(client: TestClient, version_id: str) -> tuple[str, int]:
    version = client.get(f"/api/v1/asset-versions/{version_id}").json()
    return version["review_state"], version["review_revision"]


# --- AC1: a transition and its event -----------------------------------------------------------


def test_approving_a_version_records_who_when_from_to_and_the_note(
    client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    version_id = _version(client, engine)

    response = client.post(_path(version_id), json={**APPROVE, "note": "  Rim fixed.  "})

    assert response.status_code == 201
    event = response.json()
    assert response.headers["Location"] == f"/api/v1/review-events/{event['id']}"
    assert event == {
        "id": event["id"],
        "version_id": version_id,
        "sequence": 1,
        "action": "approve",
        "from_state": "in_review",
        "to_state": "approved",
        "actor": {"id": str(user.id), "display_name": "Ada Artist"},
        "note": "Rim fixed.",
        "created_at": event["created_at"],
    }
    assert event["created_at"].replace("Z", "+00:00") == clock.now().isoformat()
    assert client.get(response.headers["Location"]).json() == event
    assert _version_state(client, version_id) == ("approved", 1)


def test_a_version_starts_in_review_with_no_history(client: TestClient, engine: Engine) -> None:
    version_id = _version(client, engine, status="pending_upload")

    assert _version_state(client, version_id) == ("in_review", 0)
    assert client.get(_history(version_id)).json() == {"items": [], "next_cursor": None}


def test_request_changes_then_reopen_then_approve_walks_the_machine(
    client: TestClient, engine: Engine
) -> None:
    version_id = _version(client, engine)

    steps = [
        _act(client, version_id, REQUEST),
        _act(client, version_id, {"action": "reopen", "expected_state": "changes_requested"}),
        _act(client, version_id, APPROVE),
        _act(client, version_id, {"action": "reopen", "expected_state": "approved"}),
    ]

    assert [(s["sequence"], s["from_state"], s["to_state"]) for s in steps] == [
        (1, "in_review", "changes_requested"),
        (2, "changes_requested", "in_review"),
        (3, "in_review", "approved"),
        (4, "approved", "in_review"),
    ]
    assert _version_state(client, version_id) == ("in_review", 4)


# --- AC2: the transition table -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("setup", "body"),
    [
        ([], {"action": "reopen", "expected_state": "in_review"}),
        ([APPROVE], {"action": "approve", "expected_state": "approved"}),
        ([APPROVE], {"action": "request_changes", "expected_state": "approved"}),
        ([REQUEST], {"action": "approve", "expected_state": "changes_requested"}),
        ([REQUEST], {"action": "request_changes", "expected_state": "changes_requested"}),
    ],
)
def test_an_action_the_table_does_not_allow_is_refused_and_nothing_changes(
    client: TestClient, engine: Engine, setup: list[dict[str, str]], body: dict[str, str]
) -> None:
    version_id = _version(client, engine)
    for step in setup:
        _act(client, version_id, step)
    before = (_events(engine), _version_state(client, version_id))

    response = client.post(_path(version_id), json=body)

    assert response.status_code == 409
    problem = response.json()
    assert problem["code"] == "INVALID_REVIEW_TRANSITION"
    assert problem["current_state"] == body["expected_state"]
    assert response.headers["content-type"] == "application/problem+json"
    assert (_events(engine), _version_state(client, version_id)) == before


@pytest.mark.parametrize(
    "body",
    [
        {"action": "merge", "expected_state": "in_review"},
        {"action": "approve", "expected_state": "rejected"},
        {"action": "approve"},
        {"expected_state": "in_review"},
        {**APPROVE, "note": 5},
        {**APPROVE, "extra": True},
    ],
)
def test_a_malformed_transition_is_a_validation_error(
    client: TestClient, engine: Engine, body: dict[str, Any]
) -> None:
    response = client.post(_path(_version(client, engine)), json=body)

    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_FAILED")
    assert _events(engine) == 0


# --- AC3: decisions need a ready version -------------------------------------------------------


@pytest.mark.parametrize("status", ["pending_upload", "processing", "failed"])
@pytest.mark.parametrize("body", [APPROVE, REQUEST])
def test_a_version_that_is_not_ready_cannot_be_approved_or_refused(
    client: TestClient, engine: Engine, status: str, body: dict[str, str]
) -> None:
    version_id = _version(client, engine, status=status)

    response = client.post(_path(version_id), json=body)

    assert (response.status_code, response.json()["code"]) == (409, "VERSION_NOT_READY")
    assert _events(engine) == 0


def test_a_decided_version_that_failed_later_can_still_be_reopened(
    client: TestClient, engine: Engine
) -> None:
    version_id = _version(client, engine)
    _act(client, version_id, APPROVE)
    _set_status(engine, version_id, "failed")

    reopened = _act(client, version_id, {"action": "reopen", "expected_state": "approved"})

    assert reopened["to_state"] == "in_review"


# --- AC4: compare-and-set ------------------------------------------------------------------------


def test_a_reviewer_who_saw_an_older_state_gets_a_conflict_with_the_current_one(
    client: TestClient, engine: Engine
) -> None:
    version_id = _version(client, engine)
    _act(client, version_id, APPROVE)  # someone else, a moment ago

    response = client.post(_path(version_id), json={**REQUEST, "note": "Too dark."})

    assert response.status_code == 409
    problem = response.json()
    assert problem["code"] == "REVIEW_STATE_CONFLICT"
    assert problem["current_state"] == "approved"
    assert problem["instance"] == _path(version_id)
    assert _events(engine) == 1
    assert _version_state(client, version_id) == ("approved", 1)


def test_unknown_versions_and_events_are_404(client: TestClient) -> None:
    missing = "0190a0a0-0000-7000-8000-000000000000"

    answers = [
        client.post(_path(missing), json=APPROVE),
        client.get(_history(missing)),
        client.get(f"/api/v1/review-events/{missing}"),
    ]

    assert [(a.status_code, a.json()["code"]) for a in answers] == [
        (404, "ASSET_VERSION_NOT_FOUND"),
        (404, "ASSET_VERSION_NOT_FOUND"),
        (404, "REVIEW_EVENT_NOT_FOUND"),
    ]


# --- AC5: notes ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "note",
    ["a" * 1001, "ok\u200b", "ok\u0000", "\u3164", "o\u202ek"],
)
def test_a_long_or_hidden_note_is_refused(client: TestClient, engine: Engine, note: str) -> None:
    version_id = _version(client, engine)

    response = client.post(_path(version_id), json={**APPROVE, "note": note})

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REVIEW_NOTE")
    assert _version_state(client, version_id) == ("in_review", 0)


@pytest.mark.parametrize("escaped", ["a\\ud800b", "\\udfff"])
def test_a_note_with_a_lone_surrogate_is_an_invalid_note(
    client: TestClient, engine: Engine, escaped: str
) -> None:
    version_id = _version(client, engine)
    raw = (
        '{"action": "approve", "expected_state": "in_review", "note": "' + escaped + '"}'
    ).encode()

    response = client.post(
        _path(version_id), content=raw, headers={"Content-Type": "application/json"}
    )

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REVIEW_NOTE")


@pytest.mark.parametrize(
    ("note", "stored"),
    [
        (None, None),
        ("   ", None),
        ("Đã sửa.\r\nDuyệt 👩\u200d🎨", "Đã sửa.\nDuyệt 👩\u200d🎨"),
        ("a" * 1000, "a" * 1000),
    ],
)
def test_a_note_is_optional_trimmed_and_kept_in_any_script(
    client: TestClient, engine: Engine, note: str | None, stored: str | None
) -> None:
    event = _act(client, _version(client, engine), {**APPROVE, "note": note})

    assert event["note"] == stored


# --- AC6: history --------------------------------------------------------------------------------


def test_history_lists_newest_first_page_by_page(client: TestClient, engine: Engine) -> None:
    version_id = _version(client, engine)
    for index in range(5):
        _act(client, version_id, {**APPROVE, "note": f"approve {index}"})
        _act(client, version_id, {"action": "reopen", "expected_state": "approved"})

    pages: list[list[int]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 3}
        if cursor is not None:
            params["cursor"] = cursor
        page = client.get(_history(version_id), params=params).json()
        pages.append([item["sequence"] for item in page["items"]])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert pages == [[10, 9, 8], [7, 6, 5], [4, 3, 2], [1]]
    newest = client.get(_history(version_id), params={"limit": 1}).json()["items"][0]
    assert (newest["action"], newest["actor"]["display_name"]) == ("reopen", "Ada Artist")


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_a_history_limit_outside_1_to_100_is_refused(
    client: TestClient, engine: Engine, limit: int
) -> None:
    response = client.get(_history(_version(client, engine)), params={"limit": limit})

    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_FAILED")


@pytest.mark.parametrize(
    "raw",
    [b"n|2147483648", b"n|" + b"9" * 40, b"n|0" + b"1" * 12, b"n|-1", b"x|1", b"\xff\xfe"],
)
def test_a_crafted_history_cursor_is_refused_not_a_server_error(
    client: TestClient, engine: Engine, raw: bytes
) -> None:
    """Every integer decoded from a cursor is bounded before it reaches the database."""
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    response = client.get(_history(_version(client, engine)), params={"cursor": cursor})

    assert (response.status_code, response.json()["code"]) == (400, "INVALID_CURSOR")


def test_the_largest_sequence_cursor_answers_an_empty_page(
    client: TestClient, engine: Engine
) -> None:
    cursor = base64.urlsafe_b64encode(b"n|2147483647").decode().rstrip("=")

    response = client.get(_history(_version(client, engine)), params={"cursor": cursor})

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


# --- AC7: the asset's state is its newest version's ----------------------------------------------


def test_the_gallery_and_the_detail_show_the_newest_versions_state(
    client: TestClient, engine: Engine
) -> None:
    version_id = _version(client, engine)
    asset_id = client.get(f"/api/v1/asset-versions/{version_id}").json()["asset_id"]
    _act(client, version_id, APPROVE)

    listed = client.get("/api/v1/assets").json()["items"][0]
    detail = client.get(f"/api/v1/assets/{asset_id}").json()
    assert (listed["review_state"], detail["review_state"]) == ("approved", "approved")
    assert detail["versions"][0]["review_state"] == "approved"

    second = client.post(
        f"/api/v1/assets/{asset_id}/versions",
        json={key: ROCK[key] for key in ("file_name", "content_type", "size_bytes")},
    )
    assert second.status_code == 201
    assert second.json()["asset"]["review_state"] == "in_review"
    detail = client.get(f"/api/v1/assets/{asset_id}").json()
    assert detail["review_state"] == "in_review"
    assert [v["review_state"] for v in detail["versions"]] == ["approved", "in_review"]
    assert client.get("/api/v1/assets").json()["items"][0]["review_state"] == "in_review"


# --- AC8: idempotency ----------------------------------------------------------------------------


def test_a_repeated_transition_with_its_key_is_recorded_once_and_replayed(
    client: TestClient, engine: Engine
) -> None:
    version_id = _version(client, engine)
    headers = {"Idempotency-Key": "review-1"}

    first = client.post(_path(version_id), json=APPROVE, headers=headers)
    again = client.post(_path(version_id), json=APPROVE, headers=headers)

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.headers["Location"] == first.headers["Location"]
    assert "Idempotent-Replayed" not in first.headers
    assert _events(engine) == 1


def test_a_key_reused_for_another_decision_is_refused(client: TestClient, engine: Engine) -> None:
    version_id = _version(client, engine)
    headers = {"Idempotency-Key": "review-2"}
    client.post(_path(version_id), json=APPROVE, headers=headers)

    reused = client.post(
        _path(version_id), json={"action": "reopen", "expected_state": "approved"}, headers=headers
    )
    other_kind = client.post(
        f"/api/v1/asset-versions/{version_id}/comment-threads",
        json={"body": "x"},
        headers=headers,
    )

    assert (reused.status_code, reused.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    assert (other_kind.status_code, other_kind.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    assert _events(engine) == 1


def test_a_refused_transition_does_not_use_up_its_key(client: TestClient, engine: Engine) -> None:
    version_id = _version(client, engine, status="processing")
    headers = {"Idempotency-Key": "review-3"}

    refused = client.post(_path(version_id), json=APPROVE, headers=headers)
    _set_status(engine, version_id, "ready")
    accepted = client.post(_path(version_id), json=APPROVE, headers=headers)

    assert refused.status_code == 409
    assert accepted.status_code == 201
    assert "Idempotent-Replayed" not in accepted.headers


# --- AC9: authorization, scopes, CSRF -------------------------------------------------------------


def test_a_read_token_reads_reviews_but_cannot_decide(
    client: TestClient, anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    version_id = _version(client, engine)
    event = _act(client, version_id, APPROVE)
    reader = _bearer(engine, user, clock, Scope.READ)

    write = anonymous_client.post(
        _path(version_id),
        json={"action": "reopen", "expected_state": "approved"},
        headers=reader,
    )
    reads = [
        anonymous_client.get(_history(version_id), headers=reader),
        anonymous_client.get(f"/api/v1/review-events/{event['id']}", headers=reader),
    ]

    assert (write.status_code, write.json()["code"]) == (403, "INSUFFICIENT_SCOPE")
    assert [r.status_code for r in reads] == [200, 200]
    assert _events(engine) == 1


def test_a_write_only_token_decides_but_cannot_read_the_history(
    client: TestClient, anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    version_id = _version(client, engine)
    writer = _bearer(engine, user, clock, Scope.WRITE)

    decided = anonymous_client.post(_path(version_id), json=APPROVE, headers=writer)
    history = anonymous_client.get(_history(version_id), headers=writer)

    assert decided.status_code == 201
    assert (history.status_code, history.json()["code"]) == (403, "INSUFFICIENT_SCOPE")


def test_anyone_in_the_studio_may_review_someone_elses_upload(
    client: TestClient, anonymous_client: TestClient, engine: Engine, clock: FixedClock
) -> None:
    """One workspace (ADR 0012, ADR 0015): a lead approves what an artist uploaded."""
    version_id = _version(client, engine)
    lead = insert_user(engine, email="lead@kiln.test", display_name="Lena Lead")

    event = anonymous_client.post(
        _path(version_id), json=APPROVE, headers=_bearer(engine, lead, clock)
    ).json()

    assert event["actor"] == {"id": str(lead.id), "display_name": "Lena Lead"}


def test_reviews_need_a_session_or_a_token(
    anonymous_client: TestClient, client: TestClient, engine: Engine
) -> None:
    version_id = _version(client, engine)
    client.headers.pop("Authorization")

    answers = [
        anonymous_client.post(_path(version_id), json=APPROVE),
        anonymous_client.get(_history(version_id)),
    ]

    assert [(a.status_code, a.json()["code"]) for a in answers] == [(401, "UNAUTHENTICATED")] * 2


def test_a_browser_session_decides_with_the_csrf_header_and_not_without(
    anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    client = anonymous_client
    client.cookies.set(SESSION_COOKIE_LOCAL, insert_session(engine, user, now=clock.now()))
    version_id = _version(client, engine)

    without = client.post(_path(version_id), json=APPROVE, headers={**APP_HEADERS, CSRF_HEADER: ""})
    other_origin = client.post(
        _path(version_id), json=APPROVE, headers={**APP_HEADERS, "Origin": "https://evil.example"}
    )
    with_header = client.post(_path(version_id), json=APPROVE)

    assert [(r.status_code, r.json()["code"]) for r in (without, other_origin)] == [
        (403, "CSRF_CHECK_FAILED")
    ] * 2
    assert with_header.status_code == 201
    assert _events(engine) == 1


def test_the_event_id_is_a_uuid_v7(client: TestClient, engine: Engine) -> None:
    event = _act(client, _version(client, engine), APPROVE)

    assert UUID(event["id"]).version == 7


# --- review round 1: the client's revision is part of the compare-and-set (ADR 0016) ----------


def test_a_client_that_read_an_older_revision_is_refused_even_in_the_same_state(
    client: TestClient, engine: Engine
) -> None:
    """ABA: A reads rev 0; B approves and reopens (rev 2, in review again); A's approve is stale."""
    version_id = _version(client, engine)
    seen = _version_state(client, version_id)  # ("in_review", 0)
    _act(client, version_id, APPROVE)
    _act(client, version_id, {"action": "reopen", "expected_state": "approved"})

    response = client.post(
        _path(version_id), json={**APPROVE, "expected_revision": seen[1], "note": "Stale"}
    )

    assert response.status_code == 409
    problem = response.json()
    assert (problem["code"], problem["current_state"], problem["current_revision"]) == (
        "REVIEW_STATE_CONFLICT",
        "in_review",
        2,
    )
    assert _events(engine) == 2
    assert _version_state(client, version_id) == ("in_review", 2)


def test_the_current_revision_is_accepted_and_a_negative_one_is_malformed(
    client: TestClient, engine: Engine
) -> None:
    version_id = _version(client, engine)

    accepted = client.post(_path(version_id), json={**APPROVE, "expected_revision": 0})
    malformed = client.post(
        _path(version_id),
        json={"action": "reopen", "expected_state": "approved", "expected_revision": -1},
    )

    assert accepted.status_code == 201
    assert (malformed.status_code, malformed.json()["code"]) == (422, "VALIDATION_FAILED")


def test_a_state_conflict_also_names_the_current_revision(
    client: TestClient, engine: Engine
) -> None:
    version_id = _version(client, engine)
    _act(client, version_id, APPROVE)

    problem = client.post(_path(version_id), json=REQUEST).json()

    assert (problem["current_state"], problem["current_revision"]) == ("approved", 1)


def test_the_same_key_with_another_note_is_refused(client: TestClient, engine: Engine) -> None:
    """The note is part of the request's fingerprint, like the action and the expected state."""
    version_id = _version(client, engine)
    headers = {"Idempotency-Key": "review-note"}
    client.post(_path(version_id), json={**APPROVE, "note": "First"}, headers=headers)

    again = client.post(_path(version_id), json={**APPROVE, "note": "Second"}, headers=headers)

    assert (again.status_code, again.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    assert _events(engine) == 1
