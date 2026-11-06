from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, text

from kiln_api.repositories.idempotency import purge_expired_keys

T0 = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)


def test_purging_removes_only_keys_older_than_the_window(engine: Engine) -> None:
    with engine.begin() as connection:
        for key, age in (("old", 25), ("fresh", 1)):
            connection.execute(
                text(
                    "INSERT INTO idempotency_keys (key, operation, request_hash, created_at)"
                    " VALUES (:key, 'create_asset', :hash, :at)"
                ),
                {"key": key, "hash": b"\x00" * 32, "at": T0 - timedelta(hours=age)},
            )

    removed = purge_expired_keys(engine, now=T0, limit=500)

    with engine.connect() as connection:
        left = connection.execute(text("SELECT key FROM idempotency_keys")).scalars().all()
    assert removed == 1
    assert left == ["fresh"]


def test_purging_keeps_a_key_of_exactly_24_hours(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO idempotency_keys (key, operation, request_hash, created_at)"
                " VALUES ('edge', 'create_asset', :hash, :at)"
            ),
            {"hash": b"\x00" * 32, "at": T0 - timedelta(hours=24)},
        )

    kept = purge_expired_keys(engine, now=T0, limit=500)
    removed = purge_expired_keys(engine, now=T0 + timedelta(microseconds=1), limit=500)

    assert (kept, removed) == (0, 1)


def test_purging_removes_at_most_a_batch_oldest_first(engine: Engine) -> None:
    with engine.begin() as connection:
        for key, age in (("oldest", 30), ("older", 28), ("old", 26)):
            connection.execute(
                text(
                    "INSERT INTO idempotency_keys (key, operation, request_hash, created_at)"
                    " VALUES (:key, 'create_asset', :hash, :at)"
                ),
                {"key": key, "hash": b"\x00" * 32, "at": T0 - timedelta(hours=age)},
            )

    removed = purge_expired_keys(engine, now=T0, limit=2)

    with engine.connect() as connection:
        left = connection.execute(text("SELECT key FROM idempotency_keys")).scalars().all()
    assert removed == 2
    assert left == ["old"]


def test_purging_uses_the_database_clock_by_default(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO idempotency_keys (key, operation, request_hash, created_at)"
                " VALUES ('ancient', 'create_asset', :hash, now() - interval '25 hours'),"
                " ('recent', 'create_asset', :hash, now() - interval '23 hours')"
            ),
            {"hash": b"\x00" * 32},
        )

    assert purge_expired_keys(engine, limit=10) == 1
