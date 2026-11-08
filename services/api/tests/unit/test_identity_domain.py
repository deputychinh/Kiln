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
    normalize_password,
    password_context_words,
    password_key,
    secret_hash,
)
from kiln_api.domain.ids import uuid7
from kiln_api.enums import ErrorCode, Scope
from kiln_api.errors import (
    CommonPasswordError,
    GuessablePasswordError,
    InvalidDisplayNameError,
    InvalidEmailError,
    InvalidTokenNameError,
    WeakPasswordError,
)

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
READ = frozenset({Scope.READ})
# A pinned stand-in for the bundled list (the real one is tested in test_common_passwords.py).
BLOCKLIST = frozenset({"passwordpassword", "1qaz2wsx3edc4rfv"})
EMAIL = "ada.lovelace@studio.com"


def _check(password: str, email: str = EMAIL) -> None:
    check_new_password(password, email=email, blocklist=BLOCKLIST)


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


@pytest.mark.parametrize("length", [14, 129])
def test_a_password_outside_15_to_128_characters_is_refused(length: int) -> None:
    with pytest.raises(WeakPasswordError) as refused:
        _check("x" * length)

    assert refused.value.code is ErrorCode.WEAK_PASSWORD


@pytest.mark.parametrize("length", [15, 128])
def test_a_password_of_15_or_128_characters_is_accepted(length: int) -> None:
    _check("x" * length)


def test_a_password_is_never_trimmed_so_spaces_count() -> None:
    _check("  " + "x" * 13)


def test_a_password_on_the_blocklist_is_refused_as_common() -> None:
    with pytest.raises(CommonPasswordError) as refused:
        _check("passwordpassword")

    assert refused.value.code is ErrorCode.COMMON_PASSWORD


@pytest.mark.parametrize(
    "variant",
    [
        "PassWordPassWord",  # case
        "PASSWORDPASSWORD",
        "\uff50\uff41\uff53\uff53\uff57\uff4f\uff52\uff44" * 2,  # full-width forms (NFKC)
        "1QAZ2wsx3EDC4rfv",
    ],
)
def test_a_case_or_width_variant_of_a_blocklisted_password_is_refused(variant: str) -> None:
    with pytest.raises(CommonPasswordError):
        _check(variant)


def test_only_the_whole_password_is_compared_with_the_blocklist() -> None:
    _check("passwordpassword!")  # 17 characters, not on the list
    _check("my passwordpassword is long")


def test_the_comparison_key_is_nfkc_case_folded() -> None:
    assert password_key("Stra\u00dfe") == password_key("STRASSE") == "strasse"
    assert password_key("\uff2b\uff29\uff2c\uff2e") == "kiln"
    assert password_key("cafe\u0301") == password_key("CAF\u00c9")


def test_the_context_words_are_kiln_the_local_part_and_its_pieces() -> None:
    assert password_context_words("Ada.Lovelace@Studio.com") == (
        "ada.lovelace",
        "lovelace",
        "kiln",
        "ada",
    )
    assert password_context_words("al@studio.com") == ("kiln",)  # two letters are ignored


@pytest.mark.parametrize(
    "password",
    [
        "Ada.Lovelace.2026!",  # the local part and a year
        "lovelace-lovelace-1",  # a piece of the local part, repeated
        "kilnkilnkilnkiln",  # the service's name
        "\uff2b\uff29\uff2c\uff2ekilnkilnkiln",  # full-width "KILN" too
        "kikilnln" * 4,  # nested: one pass leaves "kilnkilnkilnkiln", 16 characters
        "KILNpasswordpassword",  # long enough, but what is left is on the blocklist
        "kilnq7#mzr2!vb9@lp",  # 18 characters, 14 besides "kiln"
    ],
)
def test_a_password_that_leans_on_context_words_is_refused(password: str) -> None:
    with pytest.raises(GuessablePasswordError) as refused:
        _check(password)

    assert refused.value.code is ErrorCode.GUESSABLE_PASSWORD


@pytest.mark.parametrize(
    ("password", "email"),
    [
        ("kiln-glaze-recipes-for-spring", EMAIL),  # 25 characters besides "kiln"
        ("kilnq7#mzr2!vb9@lpw", EMAIL),  # exactly 15 besides "kiln"
        ("e2e-only-password-for-local-tests", "e2e@kiln.test"),  # the e2e user
    ],
)
def test_a_password_with_enough_besides_the_context_words_is_accepted(
    password: str, email: str
) -> None:
    _check(password, email)


@pytest.mark.parametrize(
    ("password", "error"),
    [
        ("short", WeakPasswordError),
        ("PasswordPassword", CommonPasswordError),
        ("Ada.Lovelace.2026!", GuessablePasswordError),
    ],
)
def test_a_refusal_says_why_without_repeating_the_password(
    password: str, error: type[WeakPasswordError]
) -> None:
    with pytest.raises(error) as refused:
        _check(password)

    assert password.casefold() not in refused.value.detail.casefold()
    assert refused.value.status == 422


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


def test_a_password_is_nfkc_normalised_so_composed_and_decomposed_forms_match() -> None:
    composed, decomposed = "caf\u00e9 au lait 42", "cafe\u0301 au lait 42"

    assert composed != decomposed
    assert normalize_password(composed) == normalize_password(decomposed) == composed
    assert normalize_password("\uff21\uff22") == "AB"  # compatibility forms fold too


def test_the_length_rule_counts_the_normalised_password() -> None:
    _check("e\u0301" * 15)  # 30 code points, 15 after NFKC

    with pytest.raises(WeakPasswordError):
        _check("e\u0301" * 14)  # 28 code points, 14 after NFKC
