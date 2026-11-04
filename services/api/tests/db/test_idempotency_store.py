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

    removed = purge_expired_keys(engine, now=T0)

    with engine.connect() as connection:
        left = connection.execute(text("SELECT key FROM idempotency_keys")).scalars().all()
    assert removed == 1
    assert left == ["fresh"]
