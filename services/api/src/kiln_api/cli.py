"""Operator commands (KILN-12): `python -m kiln_api.cli create-user` (`make create-user`).

There is no public sign-up in v0.2; the operator creates each account here. The password is
read without echo (or from stdin with `--password-stdin`) and never from the command line, so
it does not land in shell history or `ps`.
"""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence
from enum import IntEnum
from typing import TextIO

from kiln_api.adapters import load_common_passwords
from kiln_api.clock import SystemClock
from kiln_api.config import get_settings
from kiln_api.container import build_engine, build_hasher
from kiln_api.domain.ids import uuid7
from kiln_api.errors import DomainError, EmailTakenError
from kiln_api.repositories.identity import SqlIdentityStore
from kiln_api.services.identity import IdentityService


class ExitCode(IntEnum):
    """Process exit codes of the operator CLI."""

    OK = 0
    INVALID = 1
    EMAIL_TAKEN = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kiln-api", description="Kiln operator commands.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="Create a user who can sign in.")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True, help="Display name shown in the app.")
    create.add_argument(
        "--password-stdin", action="store_true", help="Read the password from stdin (scripts)."
    )
    return parser


def _read_password(from_stdin: bool, stdin: TextIO, prompt: Callable[[str], str]) -> str | None:
    if from_stdin:
        return stdin.readline().rstrip("\n")
    first = prompt("Password: ")
    if prompt("Repeat the password: ") != first:
        return None
    return first


def run(
    argv: Sequence[str],
    identity: IdentityService,
    *,
    stdin: TextIO = sys.stdin,
    out: TextIO = sys.stdout,
    prompt: Callable[[str], str] = getpass.getpass,
) -> ExitCode:
    """Run one command; I/O is injected so tests drive it without a terminal."""
    args = _parser().parse_args(argv)
    password = _read_password(args.password_stdin, stdin, prompt)
    if password is None:
        out.write("The passwords do not match.\n")
        return ExitCode.INVALID
    try:
        user = identity.create_user(args.email, args.name, password)
    except EmailTakenError as error:
        out.write(f"{error.detail}\n")
        return ExitCode.EMAIL_TAKEN
    except DomainError as error:
        out.write(f"{error.detail}\n")
        return ExitCode.INVALID
    out.write(f"Created {user.email} ({user.id}). Sign in at the web app.\n")
    return ExitCode.OK


def main() -> None:  # pragma: no cover - runs in a subprocess in test_cli.py
    """Entry point: real settings, database and Argon2."""
    engine = build_engine(get_settings())
    identity = IdentityService(
        SqlIdentityStore(engine), build_hasher(), SystemClock(), uuid7, load_common_passwords
    )
    try:
        code = run(sys.argv[1:], identity)
    finally:
        engine.dispose()
    sys.exit(code)


if __name__ == "__main__":  # pragma: no cover
    main()
