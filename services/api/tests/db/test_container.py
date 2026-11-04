from typing import Any

from sqlalchemy import text

from kiln_api.config import Settings
from kiln_api.container import build_engine, build_storage
from kiln_api.enums import Environment


def test_database_sessions_carry_lock_and_statement_timeouts(database_url: str) -> None:
    engine = build_engine(Settings(env=Environment.TEST, database_url=database_url))
    with engine.connect() as connection:
        lock = connection.execute(text("SHOW lock_timeout")).scalar_one()
        statement = connection.execute(text("SHOW statement_timeout")).scalar_one()
    engine.dispose()

    assert (lock, statement) == ("5s", "15s")


def test_the_storage_client_has_bounded_timeouts_and_attempts() -> None:
    storage = build_storage(Settings(env=Environment.TEST))
    config: Any = storage._client.meta.config  # asserting the wiring itself

    assert (config.connect_timeout, config.read_timeout) == (3, 10)
    assert config.retries == {"total_max_attempts": 2, "mode": "standard"}
    assert config.signature_version == "s3v4"
