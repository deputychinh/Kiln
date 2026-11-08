"""Comment threads, replies and region annotations through the HTTP API (KILN-10)."""

import base64
from typing import Any

import pytest
from db_fixtures import APP_HEADERS, insert_session, insert_token, insert_user
from fakes import FixedClock
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from kiln_api.constants import CSRF_HEADER, SESSION_COOKIE_LOCAL
from kiln_api.db.schema import comment_threads, comments
from kiln_api.domain.identity import User
from kiln_api.domain.ids import uuid7
from kiln_api.enums import Scope

ROCK = {
    "name": "Rock",
    "file_name": "T_Rock_01_BaseColor.png",
    "content_type": "image/png",
    "size_bytes": 2048,
}
CRATE = {
    "name": "Crate",
    "file_name": "SM_Crate.glb",
    "content_type": "model/gltf-binary",
    "size_bytes": 4096,
}
RECT = {"shape": "rect", "x": 0.25, "y": 0.5, "width": 0.5, "height": 0.25}
POINT = {"shape": "point", "x": 0.1, "y": 0.9}


def _version(client: TestClient, asset: dict[str, Any] = ROCK) -> str:
    created = client.post("/api/v1/assets", json=asset)
    assert created.status_code == 201, created.text
    version_id: str = created.json()["version"]["id"]
    return version_id


def _threads_path(version_id: str) -> str:
    return f"/api/v1/asset-versions/{version_id}/comment-threads"


def _start(client: TestClient, version_id: str, **body: Any) -> dict[str, Any]:
    response = client.post(_threads_path(version_id), json={"body": "Fix this", **body})
    assert response.status_code == 201, response.text
    thread: dict[str, Any] = response.json()
    return thread


def _bearer(engine: Engine, user: User, clock: FixedClock, *scopes: Scope) -> dict[str, str]:
    token = insert_token(engine, user, now=clock.now(), scopes=frozenset(scopes or Scope))
    return {"Authorization": f"Bearer {token}"}


def _count(engine: Engine, table: Any) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


# --- AC1: start a thread ------------------------------------------------------------------------


def test_a_thread_on_a_rectangle_is_numbered_and_returns_its_first_comment(
    client: TestClient, user: User, clock: FixedClock
) -> None:
    version_id = _version(client)

    response = client.post(
        _threads_path(version_id), json={"body": "  The rim is too bright.  ", "region": RECT}
    )

    assert response.status_code == 201
    thread = response.json()
    assert response.headers["Location"] == f"/api/v1/comment-threads/{thread['id']}"
    assert thread["number"] == 1
    assert thread["version_id"] == version_id
    assert thread["region"] == RECT
    assert thread["reply_count"] == 0
    assert thread["resolved_at"] is None
    assert thread["resolved_by"] is None
    assert thread["comment"]["body"] == "The rim is too bright."
    assert thread["comment"]["author"] == {"id": str(user.id), "display_name": "Ada Artist"}
    assert thread["comment"]["edited_at"] is None
    assert thread["comment"]["deleted"] is False
    assert thread["created_at"].replace("Z", "+00:00") == clock.now().isoformat()
    assert client.get(response.headers["Location"]).json() == thread


def test_a_point_and_a_plain_comment_are_threads_too(client: TestClient) -> None:
    version_id = _version(client)

    pin = _start(client, version_id, region=POINT)
    plain = _start(client, version_id)

    assert pin["region"] == {**POINT, "width": None, "height": None}
    assert plain["region"] is None
    assert [pin["number"], plain["number"]] == [1, 2]


def test_thread_numbers_count_per_version(client: TestClient) -> None:
    first, second = _version(client), _version(client)

    numbers = [_start(client, v)["number"] for v in (first, second, first, second, first)]

    assert numbers == [1, 1, 2, 2, 3]


def test_a_region_stays_exact_at_the_image_edges(client: TestClient) -> None:
    version_id = _version(client)
    whole = {"shape": "rect", "x": 0, "y": 0, "width": 1, "height": 1}
    corner = {"shape": "point", "x": 1, "y": 1}

    assert _start(client, version_id, region=whole)["region"] == whole
    assert _start(client, version_id, region=corner)["region"]["x"] == 1


# --- AC2: regions -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "region",
    [
        {"shape": "rect", "x": -0.01, "y": 0, "width": 0.5, "height": 0.5},
        {"shape": "rect", "x": 0, "y": 1.01, "width": 0.5, "height": 0.5},
        {"shape": "rect", "x": 0.6, "y": 0, "width": 0.5, "height": 0.5},  # past the right edge
        {"shape": "rect", "x": 0, "y": 0.6, "width": 0.5, "height": 0.5},  # past the bottom edge
        {"shape": "rect", "x": 0, "y": 0, "width": 0, "height": 0.5},
        {"shape": "rect", "x": 0, "y": 0, "width": 0.5, "height": -0.1},
        {"shape": "rect", "x": 0, "y": 0, "width": 0.5},
        {"shape": "point", "x": 0.5, "y": 0.5, "width": 0.1, "height": 0.1},
        {"shape": "point", "x": 1.5, "y": 0.5},
    ],
)
def test_a_region_outside_the_image_or_of_the_wrong_size_is_refused(
    client: TestClient, engine: Engine, region: dict[str, Any]
) -> None:
    version_id = _version(client)

    response = client.post(_threads_path(version_id), json={"body": "x", "region": region})

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REGION")
    assert _count(engine, comment_threads) == 0
    assert _count(engine, comments) == 0


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_a_region_that_is_not_a_finite_number_is_refused(client: TestClient, value: str) -> None:
    version_id = _version(client)
    raw = f'{{"body": "x", "region": {{"shape": "point", "x": {value}, "y": 0.5}}}}'

    response = client.post(
        _threads_path(version_id), content=raw, headers={"Content-Type": "application/json"}
    )

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REGION")


@pytest.mark.parametrize(
    "region",
    [
        {"shape": "circle", "x": 0.5, "y": 0.5},
        {"shape": "point", "x": "0.5", "y": 0.5},  # a string, not a number
        {"shape": "point", "x": 0.5, "y": 0.5, "z": 1},
    ],
)
def test_a_malformed_region_is_a_validation_error(
    client: TestClient, region: dict[str, Any]
) -> None:
    version_id = _version(client)

    response = client.post(_threads_path(version_id), json={"body": "x", "region": region})

    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_FAILED")


def test_a_model_takes_plain_comments_but_no_region(client: TestClient, engine: Engine) -> None:
    version_id = _version(client, CRATE)

    refused = client.post(_threads_path(version_id), json={"body": "Too dark", "region": POINT})
    plain = client.post(_threads_path(version_id), json={"body": "Too dark"})

    assert (refused.status_code, refused.json()["code"]) == (422, "REGION_NOT_SUPPORTED")
    assert plain.status_code == 201
    assert _count(engine, comment_threads) == 1


# --- AC3: bodies --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "",
        "   \n\t ",
        "x" * 2001,
        "bad\x00byte",
        "tab\tinside",
        "bell\x07",
        "hidden\u200bspace",  # zero width space (Cf)
        "\u202eevil",  # right-to-left override (Trojan Source)
        "tag\U000e0041",  # tag character
        "\u3164",  # Hangul filler only
        "line\u2028separator",
    ],
)
def test_a_blank_long_or_hidden_body_is_refused(
    client: TestClient, engine: Engine, body: str
) -> None:
    version_id = _version(client)

    response = client.post(_threads_path(version_id), json={"body": body})

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_COMMENT_BODY")
    assert _count(engine, comment_threads) == 0


@pytest.mark.parametrize(
    "body",
    [
        "Line one\nLine two",
        "Đổi màu viền sang xanh",  # Vietnamese
        "اللون غامق جدا",  # Arabic
        "रंग बदलें",  # Hindi
        "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",  # Persian "I want", with ZWNJ
        "👩\u200d🎨 looks great",  # emoji ZWJ sequence
        "色が暗すぎます",  # Japanese
        "x" * 2000,
    ],
)
def test_bodies_in_any_script_and_with_line_breaks_are_kept(client: TestClient, body: str) -> None:
    version_id = _version(client)

    assert _start(client, version_id, body=body)["comment"]["body"] == body


def test_windows_line_breaks_become_plain_ones(client: TestClient) -> None:
    version_id = _version(client)

    assert _start(client, version_id, body="a\r\nb\rc")["comment"]["body"] == "a\nb\nc"


def test_an_over_long_field_is_refused_at_the_edge(client: TestClient) -> None:
    version_id = _version(client)

    response = client.post(_threads_path(version_id), json={"body": "x" * 10_001})

    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_FAILED")


# --- AC4 and AC5: replies and lists -------------------------------------------------------------


def test_replies_are_listed_oldest_first_and_counted_on_the_thread(
    client: TestClient, clock: FixedClock
) -> None:
    thread = _start(client, _version(client))
    path = f"/api/v1/comment-threads/{thread['id']}/comments"

    created = []
    for text in ("first", "second", "third"):
        clock.advance(1)
        response = client.post(path, json={"body": text})
        assert response.status_code == 201
        assert response.headers["Location"] == f"/api/v1/comments/{response.json()['id']}"
        created.append(response.json())

    page = client.get(path).json()
    assert [c["body"] for c in page["items"]] == ["first", "second", "third"]
    assert page["next_cursor"] is None
    assert client.get(f"/api/v1/comment-threads/{thread['id']}").json()["reply_count"] == 3
    assert client.get(f"/api/v1/comments/{created[0]['id']}").json() == created[0]


def test_replies_page_with_a_cursor(client: TestClient) -> None:
    thread = _start(client, _version(client))
    path = f"/api/v1/comment-threads/{thread['id']}/comments"
    for number in range(5):
        client.post(path, json={"body": f"reply {number}"})

    first = client.get(path, params={"limit": 2}).json()
    second = client.get(path, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    third = client.get(path, params={"limit": 2, "cursor": second["next_cursor"]}).json()

    bodies = [c["body"] for page in (first, second, third) for c in page["items"]]
    assert bodies == [f"reply {n}" for n in range(5)]
    assert third["next_cursor"] is None


def test_threads_are_listed_by_number_with_a_cursor(client: TestClient) -> None:
    version_id = _version(client)
    for number in range(5):
        _start(client, version_id, body=f"note {number}")

    first = client.get(_threads_path(version_id), params={"limit": 3}).json()
    second = client.get(
        _threads_path(version_id), params={"limit": 3, "cursor": first["next_cursor"]}
    ).json()

    assert [t["number"] for t in first["items"]] == [1, 2, 3]
    assert [t["number"] for t in second["items"]] == [4, 5]
    assert second["next_cursor"] is None
    assert first["items"][0]["comment"]["body"] == "note 0"


def test_a_version_without_threads_lists_none(client: TestClient) -> None:
    assert client.get(_threads_path(_version(client))).json() == {
        "items": [],
        "next_cursor": None,
    }


@pytest.mark.parametrize("cursor", ["nonsense", "bnx0d28", "x" * 300])
def test_a_bad_cursor_is_refused(client: TestClient, cursor: str) -> None:
    thread = _start(client, _version(client))

    threads = client.get(_threads_path(thread["version_id"]), params={"cursor": cursor})
    replies = client.get(
        f"/api/v1/comment-threads/{thread['id']}/comments", params={"cursor": cursor}
    )

    assert threads.status_code in {400, 422}
    assert replies.status_code in {400, 422}
    if len(cursor) <= 256:
        assert threads.json()["code"] == "INVALID_CURSOR"
        assert replies.json()["code"] == "INVALID_CURSOR"


@pytest.mark.parametrize("limit", [0, 101])
def test_a_page_limit_outside_1_to_100_is_refused(client: TestClient, limit: int) -> None:
    response = client.get(_threads_path(_version(client)), params={"limit": limit})

    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_FAILED")


def test_unknown_versions_threads_and_comments_are_404(client: TestClient) -> None:
    unknown = uuid7()

    answers = [
        client.get(_threads_path(str(unknown))),
        client.post(_threads_path(str(unknown)), json={"body": "x"}),
        client.get(f"/api/v1/comment-threads/{unknown}"),
        client.get(f"/api/v1/comment-threads/{unknown}/comments"),
        client.post(f"/api/v1/comment-threads/{unknown}/comments", json={"body": "x"}),
        client.patch(f"/api/v1/comment-threads/{unknown}", json={"resolved": True}),
        client.get(f"/api/v1/comments/{unknown}"),
        client.patch(f"/api/v1/comments/{unknown}", json={"body": "x"}),
        client.delete(f"/api/v1/comments/{unknown}"),
    ]

    assert [(a.status_code, a.json()["code"]) for a in answers] == [
        (404, "ASSET_VERSION_NOT_FOUND"),
        (404, "ASSET_VERSION_NOT_FOUND"),
        (404, "COMMENT_THREAD_NOT_FOUND"),
        (404, "COMMENT_THREAD_NOT_FOUND"),
        (404, "COMMENT_THREAD_NOT_FOUND"),
        (404, "COMMENT_THREAD_NOT_FOUND"),
        (404, "COMMENT_NOT_FOUND"),
        (404, "COMMENT_NOT_FOUND"),
        (404, "COMMENT_NOT_FOUND"),
    ]


# --- AC6 and AC7: edit and delete, author only --------------------------------------------------


def test_the_author_edits_a_comment_and_it_is_marked_edited(
    client: TestClient, clock: FixedClock
) -> None:
    thread = _start(client, _version(client))
    clock.advance(60)

    response = client.patch(
        f"/api/v1/comments/{thread['comment']['id']}", json={"body": " Rim fixed? "}
    )

    assert response.status_code == 200
    assert response.json()["body"] == "Rim fixed?"
    assert response.json()["edited_at"].replace("Z", "+00:00") == clock.now().isoformat()
    listed = client.get(_threads_path(thread["version_id"])).json()["items"][0]
    assert listed["comment"]["body"] == "Rim fixed?"


def test_an_edit_follows_the_body_rules(client: TestClient) -> None:
    thread = _start(client, _version(client))

    response = client.patch(f"/api/v1/comments/{thread['comment']['id']}", json={"body": " "})

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_COMMENT_BODY")


def test_only_the_author_may_edit_or_delete_a_comment(
    client: TestClient, anonymous_client: TestClient, engine: Engine, clock: FixedClock
) -> None:
    thread = _start(client, _version(client))
    bob = insert_user(engine, email="bob@kiln.test", display_name="Bob")
    as_bob = _bearer(engine, bob, clock)
    path = f"/api/v1/comments/{thread['comment']['id']}"

    edit = anonymous_client.patch(path, json={"body": "Mine now"}, headers=as_bob)
    delete = anonymous_client.delete(path, headers=as_bob)

    assert [(r.status_code, r.json()["code"]) for r in (edit, delete)] == [
        (403, "NOT_COMMENT_AUTHOR")
    ] * 2
    assert client.get(path).json()["body"] == "Fix this"
    # Bob may still reply and resolve: whoever can read the asset can comment (ADR 0012).
    reply = anonymous_client.post(
        f"/api/v1/comment-threads/{thread['id']}/comments", json={"body": "On it"}, headers=as_bob
    )
    assert reply.status_code == 201
    assert reply.json()["author"]["display_name"] == "Bob"


def test_a_deleted_comment_keeps_its_place_with_an_empty_body(client: TestClient) -> None:
    thread = _start(client, _version(client))
    reply = client.post(
        f"/api/v1/comment-threads/{thread['id']}/comments", json={"body": "secret"}
    ).json()

    first = client.delete(f"/api/v1/comments/{reply['id']}")
    again = client.delete(f"/api/v1/comments/{reply['id']}")
    root = client.delete(f"/api/v1/comments/{thread['comment']['id']}")

    assert (first.status_code, again.status_code, root.status_code) == (204, 204, 204)
    replies = client.get(f"/api/v1/comment-threads/{thread['id']}/comments").json()["items"]
    assert [(c["deleted"], c["body"]) for c in replies] == [(True, "")]
    listed = client.get(f"/api/v1/comment-threads/{thread['id']}").json()
    assert (listed["comment"]["deleted"], listed["comment"]["body"]) == (True, "")
    assert listed["reply_count"] == 1


def test_a_deleted_comment_cannot_be_edited(client: TestClient) -> None:
    thread = _start(client, _version(client))
    path = f"/api/v1/comments/{thread['comment']['id']}"
    client.delete(path)

    response = client.patch(path, json={"body": "Back"})

    assert (response.status_code, response.json()["code"]) == (409, "COMMENT_DELETED")


# --- AC8: resolve and reopen --------------------------------------------------------------------


def test_anyone_who_can_comment_resolves_and_reopens_a_thread(
    client: TestClient, anonymous_client: TestClient, engine: Engine, clock: FixedClock
) -> None:
    thread = _start(client, _version(client))
    bob = insert_user(engine, email="bob@kiln.test", display_name="Bob")
    as_bob = _bearer(engine, bob, clock)
    path = f"/api/v1/comment-threads/{thread['id']}"

    resolved = anonymous_client.patch(path, json={"resolved": True}, headers=as_bob)
    clock.advance(30)
    again = client.patch(path, json={"resolved": True})
    reopened = client.patch(path, json={"resolved": False})
    reopened_again = client.patch(path, json={"resolved": False})

    assert resolved.status_code == 200
    assert resolved.json()["resolved_by"] == {"id": str(bob.id), "display_name": "Bob"}
    assert again.json()["resolved_by"]["id"] == str(bob.id)  # the first resolution is kept
    assert again.json()["resolved_at"] == resolved.json()["resolved_at"]
    assert (reopened.json()["resolved_at"], reopened.json()["resolved_by"]) == (None, None)
    assert reopened_again.status_code == 200


@pytest.mark.parametrize("body", [{"resolved": "yes"}, {"resolved": 1}, {}, {"resolved": None}])
def test_resolving_needs_a_boolean(client: TestClient, body: dict[str, Any]) -> None:
    thread = _start(client, _version(client))

    response = client.patch(f"/api/v1/comment-threads/{thread['id']}", json=body)

    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_FAILED")


def test_replying_to_a_resolved_thread_keeps_it_resolved(client: TestClient) -> None:
    thread = _start(client, _version(client))
    client.patch(f"/api/v1/comment-threads/{thread['id']}", json={"resolved": True})

    client.post(f"/api/v1/comment-threads/{thread['id']}/comments", json={"body": "Thanks"})

    assert client.get(f"/api/v1/comment-threads/{thread['id']}").json()["resolved_at"] is not None


# --- AC9: idempotency ---------------------------------------------------------------------------


def test_a_repeated_thread_with_its_key_is_stored_once_and_replayed(
    client: TestClient, engine: Engine
) -> None:
    version_id = _version(client)
    key = {"Idempotency-Key": '"thread-1"'}
    body = {"body": "Once", "region": RECT}

    first = client.post(_threads_path(version_id), json=body, headers=key)
    second = client.post(_threads_path(version_id), json=body, headers=key)

    assert (first.status_code, second.status_code) == (201, 201)
    assert second.json() == first.json()
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.headers["Location"] == first.headers["Location"]
    assert "Idempotent-Replayed" not in first.headers
    assert _count(engine, comment_threads) == 1


def test_a_repeated_reply_with_its_key_is_stored_once_and_replayed(
    client: TestClient, engine: Engine
) -> None:
    thread = _start(client, _version(client))
    path = f"/api/v1/comment-threads/{thread['id']}/comments"
    key = {"Idempotency-Key": "reply-1"}

    first = client.post(path, json={"body": "Once"}, headers=key)
    second = client.post(path, json={"body": "Once"}, headers=key)

    assert second.json() == first.json()
    assert second.headers["Idempotent-Replayed"] == "true"
    assert _count(engine, comments) == 2  # the thread's first comment and one reply


def test_a_key_reused_for_another_comment_is_refused(client: TestClient, engine: Engine) -> None:
    version_id = _version(client)
    key = {"Idempotency-Key": '"thread-2"'}
    client.post(_threads_path(version_id), json={"body": "One"}, headers=key)

    other_body = client.post(_threads_path(version_id), json={"body": "Two"}, headers=key)
    other_version = client.post(_threads_path(_version(client)), json={"body": "One"}, headers=key)

    assert (other_body.status_code, other_body.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    assert other_version.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert _count(engine, comment_threads) == 1


def test_a_refused_comment_does_not_use_up_its_key(client: TestClient) -> None:
    version_id = _version(client)
    key = {"Idempotency-Key": '"thread-3"'}

    refused = client.post(_threads_path(version_id), json={"body": " "}, headers=key)
    accepted = client.post(_threads_path(version_id), json={"body": "Now"}, headers=key)

    assert (refused.status_code, accepted.status_code) == (422, 201)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (RECT, None),
        (RECT, {**RECT, "x": 0.3}),
        (RECT, {**RECT, "y": 0.55}),
        (RECT, {**RECT, "width": 0.4}),
        (RECT, {**RECT, "height": 0.2}),
        (POINT, {**POINT, "x": 0.2}),
    ],
    ids=["region-left-out", "x", "y", "width", "height", "point-x"],
)
def test_a_thread_key_reused_with_one_other_region_field_is_refused(
    client: TestClient, engine: Engine, first: dict[str, Any], second: dict[str, Any] | None
) -> None:
    """KILN-49: the body is the same, so only the region field can tell the requests apart."""
    version_id = _version(client)
    key = {"Idempotency-Key": "thread-one-field"}
    created = client.post(
        _threads_path(version_id), json={"body": "Same", "region": first}, headers=key
    )
    assert created.status_code == 201, created.text

    again = client.post(
        _threads_path(version_id), json={"body": "Same", "region": second}, headers=key
    )

    assert (again.status_code, again.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    assert _count(engine, comment_threads) == 1


def test_a_reply_key_reused_with_another_body_or_on_another_thread_is_refused(
    client: TestClient, engine: Engine
) -> None:
    """KILN-49: the body is in the reply's fingerprint and the thread id in its operation."""
    version_id = _version(client)
    thread, other_thread = _start(client, version_id), _start(client, version_id)
    key = {"Idempotency-Key": "reply-one-field"}
    first = client.post(
        f"/api/v1/comment-threads/{thread['id']}/comments", json={"body": "Once"}, headers=key
    )
    assert first.status_code == 201, first.text

    other_body = client.post(
        f"/api/v1/comment-threads/{thread['id']}/comments", json={"body": "Twice"}, headers=key
    )
    other_place = client.post(
        f"/api/v1/comment-threads/{other_thread['id']}/comments",
        json={"body": "Once"},
        headers=key,
    )

    assert (other_body.status_code, other_body.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    assert (other_place.status_code, other_place.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")
    assert _count(engine, comments) == 3  # two first comments and one reply


# --- AC10: scopes, sign-in and CSRF -------------------------------------------------------------


def test_a_read_token_lists_comments_but_cannot_write_any(
    client: TestClient, anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    thread = _start(client, _version(client))
    reader = _bearer(engine, user, clock, Scope.READ)
    before = (_count(engine, comment_threads), _count(engine, comments))
    comment_path = f"/api/v1/comments/{thread['comment']['id']}"
    thread_path = f"/api/v1/comment-threads/{thread['id']}"

    writes = [
        anonymous_client.post(
            _threads_path(thread["version_id"]), json={"body": "x"}, headers=reader
        ),
        anonymous_client.post(f"{thread_path}/comments", json={"body": "x"}, headers=reader),
        anonymous_client.patch(thread_path, json={"resolved": True}, headers=reader),
        anonymous_client.patch(comment_path, json={"body": "x"}, headers=reader),
        anonymous_client.delete(comment_path, headers=reader),
    ]
    reads = [
        anonymous_client.get(_threads_path(thread["version_id"]), headers=reader),
        anonymous_client.get(thread_path, headers=reader),
        anonymous_client.get(f"{thread_path}/comments", headers=reader),
        anonymous_client.get(comment_path, headers=reader),
    ]

    assert [(w.status_code, w.json()["code"]) for w in writes] == [(403, "INSUFFICIENT_SCOPE")] * 5
    assert [r.status_code for r in reads] == [200] * 4
    assert (_count(engine, comment_threads), _count(engine, comments)) == before
    assert client.get(comment_path).json()["body"] == "Fix this"
    assert client.get(thread_path).json()["resolved_at"] is None


def test_a_write_only_token_cannot_read_comments(
    client: TestClient, anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    thread = _start(client, _version(client))
    writer = _bearer(engine, user, clock, Scope.WRITE)

    response = anonymous_client.get(_threads_path(thread["version_id"]), headers=writer)

    assert (response.status_code, response.json()["code"]) == (403, "INSUFFICIENT_SCOPE")


def test_comments_need_a_session_or_a_token(
    client: TestClient, anonymous_client: TestClient
) -> None:
    thread = _start(client, _version(client))
    anonymous_client.headers.pop("Authorization")

    answers = [
        anonymous_client.get(_threads_path(thread["version_id"])),
        anonymous_client.post(_threads_path(thread["version_id"]), json={"body": "x"}),
        anonymous_client.delete(f"/api/v1/comments/{thread['comment']['id']}"),
    ]

    assert [(a.status_code, a.json()["code"]) for a in answers] == [(401, "UNAUTHENTICATED")] * 3


def test_a_browser_session_comments_with_the_csrf_header_and_not_without(
    anonymous_client: TestClient, engine: Engine, user: User, clock: FixedClock
) -> None:
    client = anonymous_client
    client.cookies.set(SESSION_COOKIE_LOCAL, insert_session(engine, user, now=clock.now()))
    version_id = _version(client)

    without = client.post(
        _threads_path(version_id),
        json={"body": "x"},
        headers={**APP_HEADERS, CSRF_HEADER: ""},
    )
    other_origin = client.post(
        _threads_path(version_id),
        json={"body": "x"},
        headers={**APP_HEADERS, "Origin": "https://evil.example"},
    )
    with_header = client.post(_threads_path(version_id), json={"body": "From the app"})

    assert [(r.status_code, r.json()["code"]) for r in (without, other_origin)] == [
        (403, "CSRF_CHECK_FAILED")
    ] * 2
    assert with_header.status_code == 201
    assert _count(engine, comment_threads) == 1


def test_an_allowed_origin_may_preflight_a_comment_edit(client: TestClient) -> None:
    """Edits and resolutions are PATCH, so the CORS preflight must allow the method."""
    response = client.options(
        "/api/v1/comments/0190a0a0-0000-7000-8000-000000000000",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type,x-kiln-csrf",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


@pytest.mark.parametrize("raw", [b"n|2147483648", b"n|" + b"9" * 40, b"n|0" + b"1" * 12])
def test_a_cursor_past_the_largest_thread_number_is_refused_not_a_server_error(
    client: TestClient, raw: bytes
) -> None:
    """A crafted number cursor must never reach the database (it answered 503 before)."""
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    response = client.get(_threads_path(_version(client)), params={"cursor": cursor})

    assert (response.status_code, response.json()["code"]) == (400, "INVALID_CURSOR")


@pytest.mark.parametrize("escaped", ["a\\ud800b", "\\udfff", "x\\udbff"])
def test_a_body_with_a_lone_surrogate_is_an_invalid_comment_body(
    client: TestClient, engine: Engine, escaped: str
) -> None:
    version_id = _version(client)
    raw = f'{{"body": "{escaped}"}}'.encode()

    started = client.post(
        _threads_path(version_id), content=raw, headers={"Content-Type": "application/json"}
    )
    thread = _start(client, version_id)
    edited = client.patch(
        f"/api/v1/comments/{thread['comment']['id']}",
        content=raw,
        headers={"Content-Type": "application/json"},
    )

    assert (started.status_code, started.json()["code"]) == (422, "INVALID_COMMENT_BODY")
    assert (edited.status_code, edited.json()["code"]) == (422, "INVALID_COMMENT_BODY")
    assert _count(engine, comment_threads) == 1


@pytest.mark.parametrize("size", [1e-300, 0.0099])
def test_a_rectangle_smaller_than_one_percent_is_refused(
    client: TestClient, engine: Engine, size: float
) -> None:
    region = {"shape": "rect", "x": 0.5, "y": 0.5, "width": size, "height": 0.2}

    response = client.post(_threads_path(_version(client)), json={"body": "x", "region": region})

    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REGION")
    assert _count(engine, comment_threads) == 0


def test_a_rectangle_of_exactly_one_percent_is_kept(client: TestClient) -> None:
    region = {"shape": "rect", "x": 0.99, "y": 0.99, "width": 0.01, "height": 0.01}

    assert _start(client, _version(client), region=region)["region"] == region


@pytest.mark.parametrize(
    "position",
    [
        "9999-12-31T23:59:59.999999+00:00",
        "0001-01-01T00:00:00+14:00",
        "9999-12-31T23:59:59-23:59",
    ],
)
def test_time_cursors_at_the_ends_of_the_calendar_answer_without_a_server_error(
    client: TestClient, position: str
) -> None:
    """The other decoder (`decode_cursor`, assets and replies) has no unbounded field."""
    thread = _start(client, _version(client))
    raw = f"{position}|0190a0a0-0000-7000-8000-000000000000".encode()
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    replies = client.get(
        f"/api/v1/comment-threads/{thread['id']}/comments", params={"cursor": cursor}
    )
    assets = client.get("/api/v1/assets", params={"cursor": cursor})

    assert (replies.status_code, assets.status_code) == (200, 200)
    assert replies.json()["items"] == []
