import io

import pytest
from db_fixtures import TEST_HASHER, TEST_PASSWORD
from fakes import FixedClock
from sqlalchemy import Engine

from kiln_api.cli import ExitCode, run
from kiln_api.domain.ids import uuid7
from kiln_api.repositories.identity import SqlIdentityStore
from kiln_api.services.identity import IdentityService

ARGS = ["create-user", "--email", "Ada@Kiln.test", "--name", "Ada Artist"]


@pytest.fixture
def identity(engine: Engine) -> IdentityService:
    return IdentityService(SqlIdentityStore(engine), TEST_HASHER, FixedClock(), uuid7)


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
    assert "12 to 128 characters" in out.getvalue()
    assert "already exists" in out.getvalue()
