import json
import random
import unicodedata
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

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
from kiln_api.schemas.identity import SignInRequest

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
READ = frozenset({Scope.READ})
# A pinned stand-in for the bundled list (the real one is tested in test_common_passwords.py).
BLOCKLIST = frozenset({"passwordpassword", "1qaz2wsx3edc4rfv"})
EMAIL = "ada.lovelace@studio.com"


def _check(password: str, email: str = EMAIL, display_name: str = "") -> None:
    check_new_password(password, email=email, blocklist=BLOCKLIST, display_name=display_name)


def _refused_as_weak(password: str) -> None:
    """The length rule, exactly: not one of its subclasses (common, guessable)."""
    with pytest.raises(WeakPasswordError) as refused:
        _check(password)
    assert refused.value.code is ErrorCode.WEAK_PASSWORD


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
    _refused_as_weak("x" * length)


@pytest.mark.parametrize(
    "password",
    [
        "\ufdfa",  # one code point, 18 characters after NFKC
        "\ufb03" * 5,  # the "ffi" ligature: 5 code points, 15 after NFKC
        "\u3392" * 5,  # the "MHz" square: 5 code points, 15 after NFKC
        "x" * 14 + "\u200b",  # a zero-width space does not count
        "x" * 14 + "\ufe0f",  # nor a variation selector
        "abcdefghijklmn\t",  # nor a tab (Cc)
        "abcdefghijklmn\x00",  # nor NUL
        "abcdefghijklmn\n",  # nor a newline
        "abcdefghijklmn\x7f",  # nor DEL
        "abcdefghijklmn\u2028",  # nor a line separator (Zl)
        "abcdefghijklmn\u2029",  # nor a paragraph separator (Zp)
    ],
)
def test_each_visible_code_point_counts_once_toward_the_minimum(password: str) -> None:
    """NIST SP 800-63B-4: each code point is one character, whatever NFKC expands it to."""
    _refused_as_weak(password)


def test_a_password_of_15_compatibility_characters_counts_15() -> None:
    _check("\ufdfa" * 15)  # 270 characters after NFKC, within the hashed bound of 512


def test_the_hashed_form_is_bounded_at_exactly_512() -> None:
    _check("\ufdfa" * 28 + "x" * 8)  # 36 code points, 512 after NFKC

    _refused_as_weak("\ufdfa" * 28 + "x" * 9)  # 513 after NFKC
    _refused_as_weak("\ufdfa" * 29)  # 522 after NFKC, although only 29 code points


def test_the_typed_form_is_bounded_at_exactly_512_as_sign_in_is() -> None:
    """Decomposed accents and invisible characters do not count, but they are still sent."""
    _check("x" * 128 + "\u200b" * 384)  # 128 visible, 512 typed

    _refused_as_weak("x" * 128 + "\u200b" * 385)  # 513 typed
    _refused_as_weak("e\u0301" * 128 + "\u200b" * 384)  # 128 after NFC, 640 typed


# Characters that count once each, whatever they become after NFKC.
_VISIBLE = [
    "x",
    "e\u0301",  # decomposed: two code points typed, one after NFC
    "\u00e9",
    "\ufdfa",  # 18 characters after NFKC
    "\ufb03",
    "\u0334",  # a combining mark that never composes
    " ",
    "\U0001f525",  # an emoji outside the BMP
    "\u5bc6",  # CJK
]
# Typed, sent at sign-in, but never counted.
_UNSEEN = ["\u200b", "\t", "\u200d", "\ufe0f", "\u2028"]


def _generated_passwords(count: int) -> list[str]:
    """15-128 visible characters padded with 0-600 unseen ones, so many lie near or past the
    512-character bound, and one in five with a lone surrogate (what invalid UTF-8 on stdin
    decodes to); seeded, so a failure names the same passwords on every run."""
    rng = random.Random(39)  # noqa: S311 - test data, not a secret
    passwords = []
    for _ in range(count):
        parts = [rng.choice(_VISIBLE) for _ in range(rng.randint(15, 128))]
        parts += [rng.choice(_UNSEEN) for _ in range(rng.randint(0, 600))]
        if rng.random() < 0.2:
            parts.append(rng.choice(["\udc80", "\ud800", "\udfff"]))
        rng.shuffle(parts)
        passwords.append("".join(parts))
    return passwords


_EDGES = [
    "x" * 128,
    "x" * 128 + "\u200b" * 384,
    "\ufdfa" * 28 + "x" * 8,
    "e\u0301" * 128,
    "\U0001f525" * 128,
    "\u5bc6" * 15,
]


def _has_surrogate(password: str) -> bool:
    return any(unicodedata.category(char) == "Cs" for char in password)


def _accepted(password: str) -> bool:
    try:
        check_new_password(password, email=EMAIL, blocklist=frozenset())
    except WeakPasswordError:
        return False
    return True


@pytest.mark.parametrize("password", _EDGES)
def test_a_password_at_an_edge_that_can_be_created_can_be_sent_at_sign_in(password: str) -> None:
    assert _accepted(password)

    SignInRequest(email=EMAIL, password=password)


def test_every_password_that_can_be_created_can_be_sent_at_sign_in() -> None:
    """Property over 3,000 seeded passwords: creation never accepts what `SignInRequest` would
    refuse (review round 2: a decomposed password was accepted and could never sign in)."""
    generated = _generated_passwords(3_000)
    accepted = [password for password in generated if _accepted(password)]
    refused_at_sign_in = []
    for password in accepted:
        try:
            SignInRequest(email=EMAIL, password=password)
            # and as the browser sends it: JSON, which refuses lone surrogates
            SignInRequest.model_validate_json(json.dumps({"email": EMAIL, "password": password}))
        except ValidationError:
            refused_at_sign_in.append(len(password))

    assert sum(_has_surrogate(password) for password in generated) >= 300  # they were tried

    assert len(accepted) >= 300  # the property is exercised, not vacuous
    assert max(len(password) for password in accepted) > 400  # near the 512 bound
    assert refused_at_sign_in == []


@pytest.mark.parametrize("length", [15, 128])
def test_a_password_of_15_or_128_characters_is_accepted(length: int) -> None:
    _check("x" * length)


def test_a_password_is_never_trimmed_so_spaces_count() -> None:
    _check("  " + "x" * 13)
    _refused_as_weak("  " + "x" * 12)


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
        "passwordpa\u200bssword",  # a zero-width space
        "passwordpa\u00adssword",  # a soft hyphen
        "password\u2060password",  # a word joiner
        "pass\ufe0fwordpassword",  # a variation selector
        "pass\u034fwordpassword",  # a combining grapheme joiner (Mn, yet default-ignorable)
        "password\U000e0041password",  # a tag character
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
    assert password_key("pass\u200bwo\u00adrd") == "password"  # invisible characters dropped


def test_the_context_words_are_kiln_the_local_part_and_its_pieces() -> None:
    assert password_context_words("Ada.Lovelace@Studio.com") == (
        "ada.lovelace",
        "lovelace",
        "studio",
        "kiln",
        "ada",
    )
    assert password_context_words("al@x.com") == ("kiln",)  # short pieces and the TLD ignored
    assert password_context_words("ada_lovelace@x.com") == (
        "ada_lovelace",
        "lovelace",
        "kiln",
        "ada",
    )


def test_the_context_words_include_the_domain_and_the_display_name() -> None:
    assert password_context_words("ada@lovelace-studio.co.uk", "Grace Hopper") == (
        "lovelace-studio",
        "grace hopper",
        "lovelace",
        "hopper",
        "studio",
        "grace",
        "kiln",
        "ada",
    )


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
        "\u00df" * 8 + "kilnkiln",  # "ß" folds to "ss" but is still 8 code points, not 16
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
        ("\u00df" * 15 + "kiln", EMAIL),  # 15 code points besides "kiln"
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


def test_the_length_rule_counts_canonically_composed_code_points() -> None:
    _check("e\u0301" * 15)  # 30 code points as typed, 15 after NFC

    _refused_as_weak("e\u0301" * 14)  # 28 code points as typed, 14 after NFC


@pytest.mark.parametrize(
    ("password", "email", "display_name"),
    [
        ("lovelace_lovelace_1", "ada_lovelace@studio.com", ""),  # pieces split at "_"
        ("lovelace-studio-2026", "ada@lovelace-studio.com", ""),  # the email's domain
        ("Grace-Hopper-1906!!", EMAIL, "Grace Hopper"),  # the display name
    ],
)
def test_the_domain_display_name_and_underscored_pieces_are_context_words(
    password: str, email: str, display_name: str
) -> None:
    with pytest.raises(GuessablePasswordError):
        _check(password, email, display_name)


_RANGE_SAMPLES = [
    "\u3164",  # Hangul filler
    "\u115f",  # Hangul choseong filler
    "\u1160",  # Hangul jungseong filler
    "\uffa0",  # half-width Hangul filler
    "\U000e0100",  # variation selector supplement
    "\U000e0001",  # language tag
    "\U000e007f",  # cancel tag
    "\u034f",  # combining grapheme joiner
    "\u17b4",  # Khmer inherent vowel
    "\u180b",  # Mongolian free variation selector
    "\u2065",  # unassigned, default-ignorable
    "\ufff0",  # unassigned special
    "\U0001bca0",  # shorthand format letter overlap
    "\U0001d173",  # musical symbol begin beam
]


@pytest.mark.parametrize("char", _RANGE_SAMPLES)
def test_each_default_ignorable_code_point_neither_counts_nor_changes_the_key(char: str) -> None:
    """One sample per range of `PASSWORD_IGNORABLE_RANGES` and its ends (review round 2)."""
    _refused_as_weak("x" * 14 + char)
    assert password_key("pass" + char + "word") == "password"
    with pytest.raises(CommonPasswordError):
        _check("password" + char + "password")


def test_a_control_character_does_not_get_a_listed_password_through() -> None:
    for char in ("\t", "\n", "\x00", "\u2028"):
        with pytest.raises(CommonPasswordError):
            _check("passwordpassword" + char)


def test_combining_marks_count_as_code_points_as_nist_says() -> None:
    """NIST SP 800-63B-4: each code point counts; marks are drawn and carry meaning (ADR 0021)."""
    _check("a" + "\u0334" * 14)  # 15 code points after NFC (U+0334 composes with nothing)
    _check("\u0915\u094d\u0937" * 5)  # Devanagari "ksha" (with a virama) five times

    _refused_as_weak("a" + "\u0334" * 13)


@pytest.mark.parametrize("code_point", [0xDC80, 0xD800, 0xDFFF])
def test_a_lone_surrogate_is_refused_as_weak_with_its_own_reason(code_point: int) -> None:
    """Invalid UTF-8 decodes to lone surrogates, which Argon2 cannot encode (review round 3)."""
    with pytest.raises(WeakPasswordError) as refused:
        _check("correct-staple-horse" + chr(code_point))

    assert refused.value.code is ErrorCode.WEAK_PASSWORD
    assert "not valid text" in refused.value.detail
