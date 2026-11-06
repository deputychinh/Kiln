"""Builds `Job` values for tests, including ones that run code in a subprocess."""

from datetime import UTC, datetime
from uuid import uuid4

from kiln_api.domain.jobs import Job
from kiln_api.enums import JobKind, JobStatus


def job(*, attempts: int = 1) -> Job:
    """A running thumbnail job."""
    now = datetime(2026, 11, 6, tzinfo=UTC)
    return Job(
        id=uuid4(),
        kind=JobKind.THUMBNAIL,
        version_id=uuid4(),
        status=JobStatus.RUNNING,
        attempts=attempts,
        run_after=now,
        leased_until=now,
        last_error=None,
        created_at=now,
    )
