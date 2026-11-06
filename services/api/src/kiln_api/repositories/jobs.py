"""Postgres adapter for the `JobQueue` port (ADR 0001 §5: a queue on Postgres).

Times come from the database clock (`now()`) unless a caller passes `now` (tests), so workers
with skewed clocks agree on leases. Every state change after a claim is guarded by the claim
itself (`status = 'running'` and the attempt number), so a worker whose lease expired cannot
overwrite the state written by the worker that re-claimed the job.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Connection,
    Engine,
    Row,
    and_,
    func,
    insert,
    literal,
    or_,
    select,
    update,
)
from sqlalchemy.types import DateTime

from kiln_api.db.schema import jobs
from kiln_api.domain.jobs import Job
from kiln_api.enums import JobKind, JobStatus


def _job(row: Row[Any]) -> Job:
    return Job(
        id=row.id,
        kind=JobKind(row.kind),
        version_id=row.version_id,
        status=JobStatus(row.status),
        attempts=row.attempts,
        run_after=row.run_after,
        leased_until=row.leased_until,
        last_error=row.last_error,
        created_at=row.created_at,
    )


def _clock(now: datetime | None) -> ColumnElement[datetime]:
    return func.now() if now is None else literal(now, DateTime(timezone=True))


class SqlJobQueue:
    """Claims with `FOR UPDATE SKIP LOCKED` and a lease, so crashed workers release their jobs."""

    def __init__(self, bind: Engine | Connection) -> None:
        """Use `bind`; a `Connection` joins the caller's transaction (the outbox write)."""
        self._bind = bind

    @contextmanager
    def _write(self) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            yield self._bind
        else:
            with self._bind.begin() as connection:
                yield connection

    def enqueue(self, job: Job) -> None:
        """Store a new job."""
        with self._write() as connection:
            connection.execute(
                insert(jobs).values(
                    id=job.id,
                    kind=job.kind.value,
                    version_id=job.version_id,
                    status=job.status.value,
                    attempts=job.attempts,
                    run_after=job.run_after,
                    leased_until=job.leased_until,
                    last_error=job.last_error,
                    created_at=job.created_at,
                    updated_at=job.created_at,
                )
            )

    def claim(
        self, *, lease: timedelta, max_attempts: int, now: datetime | None = None
    ) -> Job | None:
        """Take the oldest runnable job that still has attempts left."""
        at = _clock(now)
        runnable = (
            select(jobs.c.id)
            .where(
                jobs.c.attempts < max_attempts,
                or_(
                    and_(jobs.c.status == JobStatus.QUEUED.value, jobs.c.run_after <= at),
                    and_(jobs.c.status == JobStatus.RUNNING.value, jobs.c.leased_until < at),
                ),
            )
            .order_by(jobs.c.run_after)
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        with self._write() as connection:
            row = connection.execute(
                update(jobs)
                .where(jobs.c.id == runnable)
                .values(
                    status=JobStatus.RUNNING.value,
                    attempts=jobs.c.attempts + 1,
                    leased_until=at + lease,
                    updated_at=at,
                )
                .returning(*jobs.c)
            ).first()
        return None if row is None else _job(row)

    def exhausted_jobs(self, *, max_attempts: int, now: datetime | None = None) -> list[Job]:
        """Running jobs whose lease expired with no attempts left (they crashed every time).

        Read only: burying them is guarded by the claim (status and attempt number), so two
        workers reaping the same job cannot both succeed.
        """
        with self._write() as connection:
            rows = connection.execute(
                select(jobs)
                .where(
                    jobs.c.status == JobStatus.RUNNING.value,
                    jobs.c.leased_until < _clock(now),
                    jobs.c.attempts >= max_attempts,
                )
                .limit(10)
            ).all()
        return [_job(row) for row in rows]

    def extend(self, job: Job, *, lease: timedelta, now: datetime | None = None) -> bool:
        """Push the claimed job's still-valid lease to `now + lease`.

        False if this claim no longer owns the job or its lease already expired.
        """
        at = _clock(now)
        with self._write() as connection:
            result = connection.execute(
                update(jobs)
                .where(
                    jobs.c.id == job.id,
                    jobs.c.status == JobStatus.RUNNING.value,
                    jobs.c.attempts == job.attempts,
                    # An expired lease may already be reclaimed or reaped as exhausted by another
                    # worker (a read, then a guarded write): never bring it back to life.
                    jobs.c.leased_until >= at,
                )
                .values(leased_until=at + lease, updated_at=at)
            )
        return result.rowcount == 1

    def finish(self, job: Job, *, now: datetime | None = None) -> bool:
        """Mark the claimed job done; False if this claim no longer owns it."""
        return self._set(job, now=now, status=JobStatus.DONE, leased_until=None)

    def retry(self, job: Job, *, delay: timedelta, error: str, now: datetime | None = None) -> bool:
        """Requeue the claimed job after `delay`; False if this claim no longer owns it."""
        return self._set(
            job,
            now=now,
            status=JobStatus.QUEUED,
            run_after=_clock(now) + delay,
            leased_until=None,
            last_error=error,
        )

    def bury(self, job: Job, *, error: str, now: datetime | None = None) -> bool:
        """Stop retrying the claimed job; False if this claim no longer owns it."""
        return self._set(job, now=now, status=JobStatus.DEAD, leased_until=None, last_error=error)

    def counts(self) -> dict[JobStatus, int]:
        """Jobs per status, for monitoring."""
        with self._write() as connection:
            rows = connection.execute(
                select(jobs.c.status, func.count()).group_by(jobs.c.status)
            ).all()
        return {JobStatus(status): count for status, count in rows}

    def _set(self, job: Job, *, now: datetime | None, status: JobStatus, **values: object) -> bool:
        with self._write() as connection:
            result = connection.execute(
                update(jobs)
                .where(
                    jobs.c.id == job.id,
                    jobs.c.status == JobStatus.RUNNING.value,
                    jobs.c.attempts == job.attempts,
                )
                .values(status=status.value, updated_at=_clock(now), **values)
            )
        return result.rowcount == 1
