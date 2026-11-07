from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from kiln_api.domain.identity import (
    AccessToken,
    Session,
    account_key,
    check_new_password,
    clean_display_name,
    clean_token_name,
    looks_like_access_token,
    new_access_token,
    new_session,
    normalize_email,
    secret_hash,
)
from kiln_api.domain.ids import uuid7
from kiln_api.enums import Scope
from kiln_api.errors import (
    InvalidDisplayNameError,
    InvalidEmailError,
    InvalidTokenNameError,
    WeakPasswordError,
)

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
READ = frozenset({Scope.READ})


def test_an_email_is_trimmed_and_lower_cased() -> None:
    assert normalize_email("  Ada.Artist@Studio.COM ") == "ada.artist@studio.com"


@pytest.mark.parametrize(
    "email", ["", "ada", "ada@studio", "a da@studio.com", "@studio.com", "ada@@studio.com"]
)
def test_an_email_that_cannot_be_one_is_rejected(email: str) -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email(email)


def test_an_email_over_254_characters_is_rejected() -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email("a" * 245 + "@studio.com")


def test_an_email_with_a_hidden_character_is_rejected() -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email("ada\u200b@studio.com")


@pytest.mark.parametrize("length", [11, 129])
def test_a_password_outside_12_to_128_characters_is_refused(length: int) -> None:
    with pytest.raises(WeakPasswordError):
        check_new_password("x" * length)


@pytest.mark.parametrize("length", [12, 128])
def test_a_password_of_12_or_128_characters_is_accepted(length: int) -> None:
    check_new_password("x" * length)


def test_a_password_is_never_trimmed_so_spaces_count() -> None:
    check_new_password("  " + "x" * 10)


@pytest.mark.parametrize("name", ["", "   ", "x" * 81, "Ada\u202eArtist"])
def test_a_bad_display_name_is_rejected(name: str) -> None:
    with pytest.raises(InvalidDisplayNameError):
        clean_display_name(name)


@pytest.mark.parametrize("name", ["", "x" * 81, "\u200b"])
def test_a_bad_token_name_is_rejected(name: str) -> None:
    with pytest.raises(InvalidTokenNameError):
        clean_token_name(name)


def test_a_session_id_is_random_and_only_its_hash_is_kept() -> None:
    raw_a, session_a = new_session(uuid4(), now=NOW)
    raw_b, _ = new_session(uuid4(), now=NOW)

    assert raw_a != raw_b
    assert len(raw_a) == 43  # 256 bits, URL-safe base64
    assert session_a.id_hash == secret_hash(raw_a)
    assert raw_a.encode() not in session_a.id_hash
    assert session_a.expires_at == NOW + timedelta(hours=8)


def _session(*, last_seen: datetime) -> Session:
    return Session(
        id_hash=b"\0" * 32,
        user_id=uuid4(),
        created_at=NOW,
        last_seen_at=last_seen,
        expires_at=NOW + timedelta(hours=8),
    )


def test_a_session_idle_for_30_minutes_is_over_and_one_minute_less_is_live() -> None:
    session = _session(last_seen=NOW)

    assert session.is_live(NOW + timedelta(minutes=29, seconds=59))
    assert not session.is_live(NOW + timedelta(minutes=30))


def test_a_session_ends_at_its_absolute_bound_even_when_active() -> None:
    active = _session(last_seen=NOW + timedelta(hours=7, minutes=59))

    assert active.is_live(NOW + timedelta(hours=7, minutes=59, seconds=59))
    assert not active.is_live(NOW + timedelta(hours=8))


def test_a_token_is_shown_once_with_a_prefix_and_stored_as_a_hash() -> None:
    secret, token = new_access_token(
        uuid4(),
        name="  Blender laptop ",
        scopes=READ,
        expires_in_days=30,
        now=NOW,
        new_id=uuid7,
    )

    assert secret.startswith("kiln_pat_")
    assert looks_like_access_token(secret)
    assert token.prefix == secret[:15]
    assert token.token_hash == secret_hash(secret)
    assert token.name == "Blender laptop"
    assert token.expires_at == NOW + timedelta(days=30)


@pytest.mark.parametrize("days", [0, 1, 366])
def test_a_token_lifetime_kiln_does_not_offer_is_refused(days: int) -> None:
    with pytest.raises(ValueError, match="expire"):
        new_access_token(
            uuid4(), name="CLI", scopes=READ, expires_in_days=days, now=NOW, new_id=uuid7
        )


def test_a_token_without_scopes_is_refused() -> None:
    with pytest.raises(ValueError, match="scope"):
        new_access_token(
            uuid4(), name="CLI", scopes=frozenset(), expires_in_days=7, now=NOW, new_id=uuid7
        )


def _token(**changes: object) -> AccessToken:
    _, token = new_access_token(
        uuid4(), name="CLI", scopes=READ, expires_in_days=7, now=NOW, new_id=uuid7
    )
    return AccessToken(**{**{f: getattr(token, f) for f in token.__slots__}, **changes})


def test_a_token_is_live_until_it_expires_or_is_revoked() -> None:
    token = _token()

    assert token.is_live(NOW + timedelta(days=7) - timedelta(microseconds=1))
    assert not token.is_live(NOW + timedelta(days=7))
    assert not _token(revoked_at=NOW).is_live(NOW)


@pytest.mark.parametrize(
    "value",
    ["", "kiln_pat_short", "ghp_" + "a" * 43, "kiln_pat_" + "a" * 42 + "!", "kiln_pat_" + "a" * 44],
)
def test_strings_not_shaped_like_a_token_are_recognised_without_a_lookup(value: str) -> None:
    assert not looks_like_access_token(value)


def test_throttling_counts_an_account_whatever_the_case_of_the_email() -> None:
    assert account_key(" Ada@Studio.com") == account_key("ada@studio.com")
    assert account_key("ada@studio.com") != account_key("bob@studio.com")
