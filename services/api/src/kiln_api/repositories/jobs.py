"""Postgres adapter for the `JobQueue` port (ADR 0001 §5: a queue on Postgres)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, Row, and_, func, insert, or_, select, update

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

    def claim(self, *, now: datetime, lease: timedelta) -> Job | None:
        """Take the oldest runnable job: queued and due, or running with an expired lease."""
        runnable = (
            select(jobs.c.id)
            .where(
                or_(
                    and_(jobs.c.status == JobStatus.QUEUED.value, jobs.c.run_after <= now),
                    and_(jobs.c.status == JobStatus.RUNNING.value, jobs.c.leased_until < now),
                )
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
                    leased_until=now + lease,
                    updated_at=now,
                )
                .returning(*jobs.c)
            ).first()
        return None if row is None else _job(row)

    def finish(self, job_id: UUID, *, now: datetime) -> None:
        """Mark the job done."""
        self._set(job_id, now=now, status=JobStatus.DONE, leased_until=None)

    def retry(self, job_id: UUID, *, run_after: datetime, error: str, now: datetime) -> None:
        """Put the job back in the queue for a later attempt."""
        self._set(
            job_id,
            now=now,
            status=JobStatus.QUEUED,
            run_after=run_after,
            leased_until=None,
            last_error=error,
        )

    def bury(self, job_id: UUID, *, error: str, now: datetime) -> None:
        """Stop retrying: the job is dead and stays visible."""
        self._set(job_id, now=now, status=JobStatus.DEAD, leased_until=None, last_error=error)

    def counts(self) -> dict[JobStatus, int]:
        """Jobs per status, for monitoring."""
        with self._write() as connection:
            rows = connection.execute(
                select(jobs.c.status, func.count()).group_by(jobs.c.status)
            ).all()
        return {JobStatus(status): count for status, count in rows}

    def _set(self, job_id: UUID, *, now: datetime, status: JobStatus, **values: object) -> None:
        with self._write() as connection:
            connection.execute(
                update(jobs)
                .where(jobs.c.id == job_id)
                .values(status=status.value, updated_at=now, **values)
            )
