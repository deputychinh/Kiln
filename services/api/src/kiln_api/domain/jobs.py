"""Queued work for the worker: the job record and its retry schedule."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from kiln_api.constants import JOB_BACKOFF_BASE_SECONDS, JOB_MAX_ATTEMPTS
from kiln_api.enums import JobKind, JobStatus


@dataclass(frozen=True, slots=True)
class Job:
    """One unit of background work about one version."""

    id: UUID
    kind: JobKind
    version_id: UUID
    status: JobStatus
    attempts: int
    run_after: datetime
    leased_until: datetime | None
    last_error: str | None
    created_at: datetime


def new_job(kind: JobKind, version_id: UUID, *, job_id: UUID, now: datetime) -> Job:
    """A job that may run immediately."""
    return Job(
        id=job_id,
        kind=kind,
        version_id=version_id,
        status=JobStatus.QUEUED,
        attempts=0,
        run_after=now,
        leased_until=None,
        last_error=None,
        created_at=now,
    )


def next_attempt_delay(job: Job) -> timedelta | None:
    """How long to wait after a transient failure: 5 s, 25 s, 125 s, 625 s; None once used up."""
    if job.attempts >= JOB_MAX_ATTEMPTS:
        return None
    return timedelta(seconds=JOB_BACKOFF_BASE_SECONDS * 5 ** (job.attempts - 1))
