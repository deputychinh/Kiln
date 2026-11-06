import threading
from datetime import UTC, datetime, timedelta

from fakes import FakeStorage, FixedClock
from sqlalchemy import Engine

from kiln_api.config import Settings
from kiln_api.container import build_container
from kiln_api.domain.assets import UploadSpec
from kiln_api.enums import Environment
from kiln_api.repositories.maintenance import SqlMaintenanceStore

T0 = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def test_a_run_starts_once_per_interval(engine: Engine) -> None:
    store = SqlMaintenanceStore(engine)

    assert store.try_start("cleanup", every=HOUR, now=T0) is True
    assert (
        store.try_start("cleanup", every=HOUR, now=T0 + HOUR - timedelta(microseconds=1)) is False
    )
    assert store.try_start("other", every=HOUR, now=T0) is True
    assert store.try_start("cleanup", every=HOUR, now=T0 + HOUR) is True


def test_concurrent_workers_get_exactly_one_run(engine: Engine) -> None:
    store = SqlMaintenanceStore(engine)
    barrier = threading.Barrier(8)
    results: list[bool] = []

    def contend() -> None:
        barrier.wait()
        results.append(store.try_start("cleanup", every=HOUR))  # the database clock

    threads = [threading.Thread(target=contend) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [False] * 7 + [True]


def test_stale_pending_versions_are_found_oldest_first_and_bounded(
    database_url: str, engine: Engine
) -> None:
    clock = FixedClock(T0)
    storage = FakeStorage()
    container = build_container(
        Settings(env=Environment.TEST, database_url=database_url),
        engine=engine,
        storage=storage,
        clock=clock,
    )
    spec = UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=10)
    first = container.assets.create("First", spec).version
    clock.advance(60)
    second = container.assets.create("Second", spec).version
    clock.advance(60)
    completed = container.assets.create("Done", spec)
    storage.put(completed.upload.fields["key"] if completed.upload else "", 10, "image/png")
    container.assets.complete_upload(completed.version.id)
    store = SqlMaintenanceStore(engine)
    day = timedelta(hours=24)

    at_24h_of_first = T0 + day
    assert store.stale_pending_versions(older_than=day, limit=10, now=at_24h_of_first) == []
    later = T0 + day + timedelta(minutes=5)
    assert store.stale_pending_versions(older_than=day, limit=10, now=later) == [
        first.id,
        second.id,
    ]
    assert store.stale_pending_versions(older_than=day, limit=1, now=later) == [first.id]
