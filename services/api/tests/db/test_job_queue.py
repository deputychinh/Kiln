import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, create_engine, text

from kiln_api.domain.assets import UploadSpec, new_asset
from kiln_api.domain.ids import uuid7
from kiln_api.domain.jobs import Job, new_job, next_attempt_delay
from kiln_api.enums import JobKind, JobStatus
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.jobs import SqlJobQueue

T0 = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
LEASE = timedelta(minutes=5)
MAX = 5
PNG = UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=1)


def _enqueue(engine: Engine, *, at: datetime = T0) -> UUID:
    asset, version = new_asset("Rock", PNG, now=at, new_id=uuid7)
    SqlAssetRepository(engine).add(asset, version)
    job = new_job(JobKind.THUMBNAIL, version.id, job_id=uuid7(), now=at)
    SqlJobQueue(engine).enqueue(job)
    return job.id


def _claim(queue: SqlJobQueue, at: datetime = T0) -> Job | None:
    return queue.claim(lease=LEASE, max_attempts=MAX, now=at)


def test_a_queued_job_is_claimed_with_a_lease_and_one_attempt(engine: Engine) -> None:
    job_id = _enqueue(engine)

    job = _claim(SqlJobQueue(engine))

    assert job is not None
    assert (job.id, job.status, job.attempts) == (job_id, JobStatus.RUNNING, 1)
    assert job.leased_until == T0 + LEASE


def test_nothing_is_claimed_before_run_after_or_when_empty(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    assert _claim(queue) is None

    _enqueue(engine, at=T0 + timedelta(seconds=30))

    assert _claim(queue) is None
    assert _claim(queue, T0 + timedelta(seconds=30)) is not None


def test_two_workers_never_claim_the_same_job(engine: Engine) -> None:
    for _ in range(10):
        _enqueue(engine)
    claimed: list[UUID] = []
    barrier = threading.Barrier(4)

    def drain() -> None:
        queue = SqlJobQueue(engine)
        barrier.wait()
        while (job := _claim(queue)) is not None:
            claimed.append(job.id)

    threads = [threading.Thread(target=drain) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(claimed) == len(set(claimed)) == 10


def test_a_locked_job_is_skipped_without_waiting(engine: Engine, database_url: str) -> None:
    first = _enqueue(engine)
    second = _enqueue(engine, at=T0 + timedelta(seconds=1))
    impatient = create_engine(database_url, connect_args={"options": "-c lock_timeout=1000"})
    with engine.begin() as holder:
        holder.execute(text("SELECT id FROM jobs WHERE id = :id FOR UPDATE"), {"id": first})
        started = time.monotonic()
        job = _claim(SqlJobQueue(impatient), T0 + timedelta(seconds=1))
        waited = time.monotonic() - started
    impatient.dispose()

    assert job is not None
    assert job.id == second
    assert waited < 0.5


def test_a_running_job_whose_lease_expired_is_claimed_again(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    job_id = _enqueue(engine)
    _claim(queue)

    still_leased = _claim(queue, T0 + LEASE)
    reclaimed = _claim(queue, T0 + LEASE + timedelta(seconds=1))

    assert still_leased is None
    assert reclaimed is not None
    assert (reclaimed.id, reclaimed.attempts) == (job_id, 2)


def test_a_stale_claim_cannot_change_a_job_another_worker_reclaimed(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    _enqueue(engine)
    stale = _claim(queue)
    fresh = _claim(queue, T0 + LEASE + timedelta(seconds=1))
    assert stale is not None
    assert fresh is not None

    assert queue.finish(stale, now=T0) is False
    assert queue.retry(stale, delay=timedelta(seconds=5), error="x", now=T0) is False
    assert queue.bury(stale, error="x", now=T0) is False
    assert queue.counts() == {JobStatus.RUNNING: 1}
    assert queue.finish(fresh, now=T0) is True


def test_a_job_with_no_attempts_left_is_never_leased_again_but_can_be_buried(
    engine: Engine,
) -> None:
    queue = SqlJobQueue(engine)
    job_id = _enqueue(engine)
    at = T0
    for _ in range(MAX):  # every attempt "crashes": the lease just expires
        assert _claim(queue, at) is not None
        at += LEASE + timedelta(seconds=1)

    assert _claim(queue, at) is None
    exhausted = queue.exhausted_jobs(max_attempts=MAX, now=at)
    assert [job.id for job in exhausted] == [job_id]
    assert queue.bury(exhausted[0], error="crashed", now=at) is True
    assert queue.counts() == {JobStatus.DEAD: 1}


def test_finished_jobs_are_never_claimed_again(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    _enqueue(engine)
    job = _claim(queue)
    assert job is not None

    assert queue.finish(job, now=T0) is True

    assert _claim(queue, T0 + timedelta(days=1)) is None
    assert queue.counts() == {JobStatus.DONE: 1}


def test_a_retried_job_waits_for_its_delay(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    _enqueue(engine)
    job = _claim(queue)
    assert job is not None

    queue.retry(job, delay=timedelta(seconds=5), error="StorageUnavailable", now=T0)

    assert _claim(queue, T0 + timedelta(seconds=4)) is None
    again = _claim(queue, T0 + timedelta(seconds=5))
    assert again is not None
    assert (again.last_error, again.attempts) == ("StorageUnavailable", 2)


def test_the_database_clock_is_used_when_no_time_is_given(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    _enqueue(engine, at=datetime.now(UTC) - timedelta(minutes=1))

    job = queue.claim(lease=LEASE, max_attempts=MAX)

    assert job is not None
    assert job.leased_until is not None
    assert abs(job.leased_until - (datetime.now(UTC) + LEASE)) < timedelta(seconds=30)
    assert queue.retry(job, delay=timedelta(hours=1), error="x") is True
    assert queue.claim(lease=LEASE, max_attempts=MAX) is None


def test_backoff_is_5_25_125_625_seconds_then_gives_up_after_5_attempts() -> None:
    job = new_job(JobKind.THUMBNAIL, uuid7(), job_id=uuid7(), now=T0)

    delays = [next_attempt_delay(replace(job, attempts=n)) for n in range(1, 6)]

    assert delays == [
        timedelta(seconds=5),
        timedelta(seconds=25),
        timedelta(seconds=125),
        timedelta(seconds=625),
        None,
    ]


def test_the_oldest_runnable_job_is_claimed_first(engine: Engine) -> None:
    newer = _enqueue(engine, at=T0)
    older = _enqueue(engine, at=T0 - timedelta(minutes=1))

    first = _claim(SqlJobQueue(engine))

    assert first is not None
    assert first.id == older != newer


def _leased_until(engine: Engine, job_id: UUID) -> datetime:
    with engine.connect() as connection:
        value: datetime = connection.execute(
            text("SELECT leased_until FROM jobs WHERE id = :id"), {"id": job_id}
        ).scalar_one()
    return value


def test_extending_moves_the_lease_and_keeps_the_job_running(engine: Engine) -> None:
    job_id = _enqueue(engine)
    queue = SqlJobQueue(engine)
    job = _claim(queue)
    assert job is not None

    assert queue.extend(job, lease=LEASE, now=T0 + timedelta(minutes=4)) is True

    assert _leased_until(engine, job_id) == T0 + timedelta(minutes=9)
    assert _claim(queue, T0 + timedelta(minutes=6)) is None  # not expired any more
    assert queue.finish(job, now=T0 + timedelta(minutes=7)) is True  # the claim still owns it


def test_a_stale_claim_cannot_extend_a_reclaimed_or_finished_job(engine: Engine) -> None:
    _enqueue(engine)
    queue = SqlJobQueue(engine)
    first = _claim(queue)
    assert first is not None
    second = _claim(queue, T0 + LEASE + timedelta(seconds=1))  # the first lease expired
    assert second is not None

    assert queue.extend(first, lease=LEASE, now=T0 + LEASE + timedelta(seconds=2)) is False
    assert queue.finish(second, now=T0 + LEASE + timedelta(seconds=3)) is True
    assert queue.extend(second, lease=LEASE, now=T0 + LEASE + timedelta(seconds=4)) is False
