import pytest

from kiln_api.config import Settings
from kiln_api.enums import Environment


@pytest.mark.parametrize(
    ("env", "secure", "expected"),
    [
        (Environment.LOCAL, "", (False, "kiln_session")),
        (Environment.PRODUCTION, "", (True, "__Host-kiln_session")),
        (Environment.LOCAL, "true", (True, "__Host-kiln_session")),
        (Environment.PRODUCTION, "false", (False, "kiln_session")),
    ],
)
def test_the_cookie_is_secure_in_production_unless_set_otherwise(
    env: Environment, secure: str, expected: tuple[bool, str]
) -> None:
    settings = Settings(env=env, secure_cookies=secure)

    assert (settings.cookie_secure, settings.session_cookie_name) == expected


def test_the_trusted_origins_are_the_cors_allow_list() -> None:
    settings = Settings(cors_origins=["https://kiln.studio.example"])

    assert settings.trusted_origins == frozenset({"https://kiln.studio.example"})
