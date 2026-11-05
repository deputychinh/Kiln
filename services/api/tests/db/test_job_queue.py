import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine

from kiln_api.domain.assets import UploadSpec, new_asset
from kiln_api.domain.ids import uuid7
from kiln_api.domain.jobs import new_job, next_attempt_at
from kiln_api.enums import JobKind, JobStatus
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.jobs import SqlJobQueue

T0 = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
LEASE = timedelta(minutes=5)
PNG = UploadSpec(file_name="rock.png", content_type="image/png", size_bytes=1)


def _version_id(engine: Engine) -> UUID:
    asset, version = new_asset("Rock", PNG, now=T0, new_id=uuid7)
    SqlAssetRepository(engine).add(asset, version)
    return version.id


def _enqueue(engine: Engine, *, at: datetime = T0) -> UUID:
    job = new_job(JobKind.THUMBNAIL, _version_id(engine), job_id=uuid7(), now=at)
    SqlJobQueue(engine).enqueue(job)
    return job.id


def test_a_queued_job_is_claimed_with_a_lease_and_one_attempt(engine: Engine) -> None:
    job_id = _enqueue(engine)

    job = SqlJobQueue(engine).claim(now=T0, lease=LEASE)

    assert job is not None
    assert job.id == job_id
    assert job.status is JobStatus.RUNNING
    assert job.attempts == 1
    assert job.leased_until == T0 + LEASE


def test_nothing_is_claimed_before_run_after_or_when_empty(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    assert queue.claim(now=T0, lease=LEASE) is None

    _enqueue(engine, at=T0 + timedelta(seconds=30))

    assert queue.claim(now=T0, lease=LEASE) is None
    assert queue.claim(now=T0 + timedelta(seconds=30), lease=LEASE) is not None


def test_two_workers_never_claim_the_same_job(engine: Engine) -> None:
    for _ in range(10):
        _enqueue(engine)
    claimed: list[UUID] = []
    barrier = threading.Barrier(4)

    def drain() -> None:
        queue = SqlJobQueue(engine)
        barrier.wait()
        while (job := queue.claim(now=T0, lease=LEASE)) is not None:
            claimed.append(job.id)

    threads = [threading.Thread(target=drain) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(claimed) == 10
    assert len(set(claimed)) == 10


def test_a_running_job_whose_lease_expired_is_claimed_again(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    job_id = _enqueue(engine)
    queue.claim(now=T0, lease=LEASE)

    still_leased = queue.claim(now=T0 + LEASE, lease=LEASE)
    reclaimed = queue.claim(now=T0 + LEASE + timedelta(seconds=1), lease=LEASE)

    assert still_leased is None
    assert reclaimed is not None
    assert reclaimed.id == job_id
    assert reclaimed.attempts == 2


def test_finished_jobs_are_never_claimed_again(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    _enqueue(engine)
    job = queue.claim(now=T0, lease=LEASE)
    assert job is not None

    queue.finish(job.id, now=T0)

    assert queue.claim(now=T0 + timedelta(days=1), lease=LEASE) is None
    assert queue.counts() == {JobStatus.DONE: 1}


def test_a_retried_job_waits_until_its_next_attempt(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    _enqueue(engine)
    job = queue.claim(now=T0, lease=LEASE)
    assert job is not None

    queue.retry(job.id, run_after=T0 + timedelta(seconds=5), error="StorageUnavailable", now=T0)

    assert queue.claim(now=T0 + timedelta(seconds=4), lease=LEASE) is None
    again = queue.claim(now=T0 + timedelta(seconds=5), lease=LEASE)
    assert again is not None
    assert again.last_error == "StorageUnavailable"
    assert again.attempts == 2


def test_a_buried_job_is_dead_and_counted(engine: Engine) -> None:
    queue = SqlJobQueue(engine)
    _enqueue(engine)
    _enqueue(engine)
    job = queue.claim(now=T0, lease=LEASE)
    assert job is not None

    queue.bury(job.id, error="gave up", now=T0)

    assert queue.counts() == {JobStatus.DEAD: 1, JobStatus.QUEUED: 1}


def test_backoff_is_5_25_125_625_seconds_then_gives_up_after_5_attempts() -> None:
    job = new_job(JobKind.THUMBNAIL, uuid7(), job_id=uuid7(), now=T0)

    delays = [next_attempt_at(replace(job, attempts=n), now=T0) for n in range(1, 6)]

    assert [None if d is None else d - T0 for d in delays] == [
        timedelta(seconds=5),
        timedelta(seconds=25),
        timedelta(seconds=125),
        timedelta(seconds=625),
        None,
    ]
