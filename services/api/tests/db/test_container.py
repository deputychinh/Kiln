from datetime import UTC, datetime, tzinfo
from typing import Any

import pytest
from sqlalchemy import Engine, text

from kiln_api import clock as kiln_clock
from kiln_api.clock import DatabaseClock
from kiln_api.config import Settings
from kiln_api.constants import DB_CONNECT_TIMEOUT_SECONDS
from kiln_api.container import build_engine, build_storage
from kiln_api.enums import Environment


def test_database_sessions_carry_lock_and_statement_timeouts(database_url: str) -> None:
    engine = build_engine(Settings(env=Environment.TEST, database_url=database_url))
    with engine.connect() as connection:
        lock = connection.execute(text("SHOW lock_timeout")).scalar_one()
        statement = connection.execute(text("SHOW statement_timeout")).scalar_one()
    engine.dispose()

    assert (lock, statement) == ("5s", "15s")


def test_database_sockets_give_up_on_a_dead_link(database_url: str) -> None:
    """A link that dies without FIN or RST fails the session instead of blocking it (KILN-28)."""
    engine = build_engine(Settings(env=Environment.TEST, database_url=database_url))
    with engine.connect() as connection:
        dsn = connection.connection.dbapi_connection.info.dsn  # type: ignore[union-attr]
    engine.dispose()

    for setting in (
        "keepalives=1",
        "keepalives_idle=10",
        "keepalives_interval=5",
        "keepalives_count=3",
        "tcp_user_timeout=30000",
    ):
        assert setting in dsn


def test_the_storage_client_has_bounded_timeouts_and_attempts() -> None:
    storage = build_storage(Settings(env=Environment.TEST))
    config: Any = storage._client.meta.config  # asserting the wiring itself

    assert (config.connect_timeout, config.read_timeout) == (3, 10)
    assert config.retries == {"total_max_attempts": 2, "mode": "standard"}
    assert config.signature_version == "s3v4"


def test_readiness_uses_a_one_second_single_attempt_probe_client() -> None:
    storage = build_storage(Settings(env=Environment.TEST))
    probe: Any = storage._probe.meta.config  # asserting the wiring itself

    assert storage._probe is not storage._client
    assert (probe.connect_timeout, probe.read_timeout) == (1, 1)
    assert probe.retries == {"total_max_attempts": 1, "mode": "standard"}


def test_the_database_clock_reports_postgres_time_in_utc(engine: Engine) -> None:
    with engine.connect() as connection:
        before = connection.execute(text("SELECT clock_timestamp()")).scalar_one()
    moment = DatabaseClock(engine).now()
    with engine.connect() as connection:
        after = connection.execute(text("SELECT clock_timestamp()")).scalar_one()

    assert moment.tzinfo is UTC
    assert before <= moment <= after


def test_the_database_clock_ignores_a_skewed_local_clock(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SkewedDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> "SkewedDatetime":
            return cls(2000, 1, 1, tzinfo=tz)

    monkeypatch.setattr(kiln_clock, "datetime", SkewedDatetime)

    assert DatabaseClock(engine).now().year >= 2026


def test_the_engine_gives_up_connecting_after_a_few_seconds(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_create_engine(_url: str, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("kiln_api.container.create_engine", fake_create_engine)

    build_engine(Settings(env=Environment.TEST, database_url=database_url))

    assert captured["connect_args"]["connect_timeout"] == DB_CONNECT_TIMEOUT_SECONDS
