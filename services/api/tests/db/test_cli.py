import io
import os
import subprocess
import sys

import pytest
from db_fixtures import TEST_HASHER, TEST_PASSWORD
from fakes import FixedClock
from sqlalchemy import Engine

from kiln_api.adapters import load_common_passwords
from kiln_api.cli import ExitCode, run
from kiln_api.domain.ids import uuid7
from kiln_api.repositories.identity import SqlIdentityStore
from kiln_api.services.identity import IdentityService

ARGS = ["create-user", "--email", "Ada@Kiln.test", "--name", "Ada Artist"]


@pytest.fixture
def identity(engine: Engine) -> IdentityService:
    return IdentityService(
        SqlIdentityStore(engine), TEST_HASHER, FixedClock(), uuid7, load_common_passwords
    )


def test_create_user_asks_twice_without_echo_and_stores_an_argon2id_hash(
    identity: IdentityService, engine: Engine
) -> None:
    out = io.StringIO()
    prompts: list[str] = []

    def prompt(text: str) -> str:
        prompts.append(text)
        return TEST_PASSWORD

    code = run(ARGS, identity, out=out, prompt=prompt)

    assert code is ExitCode.OK
    assert len(prompts) == 2
    assert "Created ada@kiln.test" in out.getvalue()
    assert TEST_PASSWORD not in out.getvalue()
    user = SqlIdentityStore(engine).user_by_email("ada@kiln.test")
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")


def test_create_user_reads_the_password_from_stdin_for_scripts(identity: IdentityService) -> None:
    code = run(
        [*ARGS, "--password-stdin"],
        identity,
        stdin=io.StringIO(TEST_PASSWORD + "\n"),
        out=io.StringIO(),
    )

    assert code is ExitCode.OK
    assert identity.sign_in("ada@kiln.test", TEST_PASSWORD, client_ip="cli").principal


def test_create_user_stops_when_the_passwords_differ(identity: IdentityService) -> None:
    answers = iter([TEST_PASSWORD, TEST_PASSWORD + "!"])
    out = io.StringIO()

    assert run(ARGS, identity, out=out, prompt=lambda _: next(answers)) is ExitCode.INVALID
    assert "do not match" in out.getvalue()


def test_create_user_refuses_a_short_password_and_a_taken_email(
    identity: IdentityService,
) -> None:
    out = io.StringIO()

    short = run(ARGS, identity, out=out, prompt=lambda _: "short")
    run(ARGS, identity, out=io.StringIO(), prompt=lambda _: TEST_PASSWORD)
    taken = run(ARGS, identity, out=out, prompt=lambda _: TEST_PASSWORD)

    assert (short, taken) == (ExitCode.INVALID, ExitCode.EMAIL_TAKEN)
    assert "15 to 128 characters" in out.getvalue()
    assert "already exists" in out.getvalue()


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("1qaz2wsx3edc4rfv", "list of common or breached passwords"),  # on the bundled list
        ("LinkedInLinkedIn", "list of common or breached passwords"),  # its case variant
        ("Ada-Artist-at-Kiln-1", "leans on the email address, the person's name or the word Kiln"),
        (
            "artist-artist-artist-1",
            "leans on the email address, the person's name or the word Kiln",
        ),  # the name
    ],
)
def test_create_user_refuses_a_common_or_guessable_password_and_says_why(
    identity: IdentityService, engine: Engine, password: str, reason: str
) -> None:
    out = io.StringIO()

    code = run([*ARGS, "--password-stdin"], identity, stdin=io.StringIO(password + "\n"), out=out)

    assert code is ExitCode.INVALID
    assert reason in out.getvalue()
    assert password.casefold() not in out.getvalue().casefold()
    assert SqlIdentityStore(engine).user_by_email("ada@kiln.test") is None


def test_the_installed_command_refuses_a_breached_password(
    database_url: str, engine: Engine
) -> None:
    """`make create-user` as the operator runs it: a new process, its own wiring and list."""
    result = subprocess.run(  # noqa: S603 - our own interpreter and module
        [sys.executable, "-m", "kiln_api.cli", *ARGS, "--password-stdin"],
        input="passwordpassword\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**os.environ, "KILN_DATABASE_URL": database_url},
    )

    assert result.returncode == ExitCode.INVALID
    assert "list of common or breached passwords" in result.stdout
    assert "passwordpassword" not in result.stdout + result.stderr
    assert SqlIdentityStore(engine).user_by_email("ada@kiln.test") is None


def test_create_user_refuses_a_lone_surrogate_without_crashing(
    identity: IdentityService, engine: Engine
) -> None:
    out = io.StringIO()

    code = run(
        [*ARGS, "--password-stdin"],
        identity,
        stdin=io.StringIO("correct-staple-horse\udc80\n"),
        out=out,
    )

    assert code is ExitCode.INVALID
    assert "not valid text" in out.getvalue()
    assert SqlIdentityStore(engine).user_by_email("ada@kiln.test") is None


def test_the_installed_command_refuses_invalid_utf8_without_a_traceback(
    database_url: str, engine: Engine
) -> None:
    """Python decodes invalid UTF-8 on stdin to lone surrogates; Argon2 crashed on them."""
    result = subprocess.run(  # noqa: S603 - our own interpreter and module
        [sys.executable, "-m", "kiln_api.cli", *ARGS, "--password-stdin"],
        input=b"correct-staple-horse\xff\n",
        capture_output=True,
        timeout=60,
        check=False,
        env={**os.environ, "KILN_DATABASE_URL": database_url},
    )

    assert result.returncode == ExitCode.INVALID
    assert b"not valid text" in result.stdout
    assert b"Traceback" not in result.stderr
    assert SqlIdentityStore(engine).user_by_email("ada@kiln.test") is None
