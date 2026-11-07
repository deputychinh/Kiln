"""Parallel sign-ins never check more passwords than the throttle allows (review V2)."""

import threading
import time
from contextlib import suppress

from db_fixtures import TEST_HASHER, insert_user
from fakes import FixedClock
from sqlalchemy import Engine, create_engine, text

from kiln_api.domain.ids import uuid7
from kiln_api.errors import InvalidCredentialsError, SignInThrottledError
from kiln_api.repositories.identity import SqlIdentityStore
from kiln_api.services.identity import IdentityService

CALLERS = 30


class _SlowCountingHasher:
    """Real Argon2id, slowed so every caller is inside a check at the same time."""

    def __init__(self) -> None:
        self.checks = 0
        self._lock = threading.Lock()

    def hash(self, password: str) -> str:
        return TEST_HASHER.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        with self._lock:
            self.checks += 1
        time.sleep(0.2)
        return TEST_HASHER.verify(password_hash, password)

    def needs_rehash(self, _password_hash: str) -> bool:
        return False


def test_thirty_parallel_wrong_passwords_check_exactly_ten(
    database_url: str, engine: Engine
) -> None:
    insert_user(engine)
    # Every caller gets its own connection, so only the advisory locks can serialise them.
    pooled = create_engine(database_url, pool_size=CALLERS, max_overflow=0)
    hasher = _SlowCountingHasher()
    identity = IdentityService(SqlIdentityStore(pooled), hasher, FixedClock(), uuid7)
    start = threading.Barrier(CALLERS)
    outcomes: list[str] = []

    def attempt(number: int) -> None:
        start.wait()
        try:
            identity.sign_in("ada@kiln.test", "wrong password!", client_ip=f"198.51.100.{number}")
        except InvalidCredentialsError:
            outcomes.append("invalid")
        except SignInThrottledError:
            outcomes.append("throttled")

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(CALLERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    pooled.dispose()

    assert hasher.checks == 10
    assert sorted(outcomes) == ["invalid"] * 10 + ["throttled"] * 20
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM sign_in_failures")).scalar() == 10


def test_parallel_attempts_from_one_address_respect_its_limit(database_url: str) -> None:
    pooled = create_engine(database_url, pool_size=CALLERS, max_overflow=0)
    hasher = _SlowCountingHasher()
    identity = IdentityService(SqlIdentityStore(pooled), hasher, FixedClock(), uuid7)
    # Pre-fill 40 failures from one address (each for its own account), then race 30 more.
    for number in range(40):
        with suppress(InvalidCredentialsError):
            identity.sign_in(f"guess{number}@kiln.test", "x", client_ip="203.0.113.9")
    hasher.checks = 0
    start = threading.Barrier(CALLERS)

    def attempt(number: int) -> None:
        start.wait()
        with suppress(InvalidCredentialsError, SignInThrottledError):
            identity.sign_in(f"race{number}@kiln.test", "x", client_ip="203.0.113.9")

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(CALLERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    pooled.dispose()

    assert hasher.checks == 10  # 50 per address, 40 already spent
