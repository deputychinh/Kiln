"""Lease heartbeat (KILN-24): keep a long job's lease while it is making progress."""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Self

from sqlalchemy.exc import SQLAlchemyError

from kiln_api.constants import (
    JOB_HEARTBEAT_JOIN_SECONDS,
    JOB_HEARTBEAT_SECONDS,
    JOB_LEASE_SECONDS,
    JOB_MAX_RUNTIME_SECONDS,
)
from kiln_api.domain.jobs import Job
from kiln_api.enums import ErrorCode
from kiln_api.ports import JobQueue

logger = logging.getLogger("kiln_worker")


@dataclass(frozen=True, slots=True)
class LeaseTiming:
    """How long a claim lasts, how often a running job extends it, and for how long at most."""

    lease: timedelta = timedelta(seconds=JOB_LEASE_SECONDS)
    heartbeat_seconds: float = JOB_HEARTBEAT_SECONDS
    max_runtime_seconds: float = JOB_MAX_RUNTIME_SECONDS
    join_seconds: float = JOB_HEARTBEAT_JOIN_SECONDS


class LeaseHeartbeat:
    """While in its `with` block, extends `job`'s lease every `timing.heartbeat_seconds`.

    It stops when the block ends, when the claim turns out to be lost (another worker owns the
    job now), or after `timing.max_runtime_seconds`, so a hung job's lease still expires.
    """

    def __init__(
        self,
        jobs: JobQueue,
        job: Job,
        *,
        timing: LeaseTiming,
        queue_now: Callable[[], datetime | None],
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Extend `job` on `jobs`; `queue_now` is None for the database clock (as in `Worker`)."""
        self._jobs = jobs
        self._job = job
        self._lease = timing.lease
        self._interval = timing.heartbeat_seconds
        self._max_runtime = timing.max_runtime_seconds
        self._join_seconds = timing.join_seconds
        self._started = 0.0
        self._queue_now = queue_now
        self._monotonic = monotonic
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._beat, name=f"lease-heartbeat-{job.id}", daemon=True
        )
        self.lost = False

    def __enter__(self) -> Self:
        """Start beating."""
        self._started = self._monotonic()
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop at once and wait for the thread, whatever ended the block."""
        self.stop()

    def stop(self) -> None:
        """Stop extending and wait for an extension in flight (bounded); safe to call twice.

        The worker calls it before writing the job's outcome, so no extension races the write and
        a refusal after the job finished is never mistaken for a lost claim.
        """
        self._stop.set()
        if not self._thread.is_alive():
            return
        self._thread.join(self._join_seconds)
        if self._thread.is_alive():
            logger.warning(
                "job %s: a lease extension is still pending after %.0f s; moving on",
                self._job.id,
                self._join_seconds,
            )

    def _beat(self) -> None:
        while not self._stop.wait(self._interval):
            if self._monotonic() - self._started >= self._max_runtime:
                logger.warning(
                    "job %s still running after %.0f s; no longer extending its lease",
                    self._job.id,
                    self._max_runtime,
                )
                return
            try:
                extended = self._jobs.extend(self._job, lease=self._lease, now=self._queue_now())
            except Exception as error:
                cause = _cause(error)
                logger.warning("job %s: lease extension failed (%s); retrying", self._job.id, cause)
                continue
            if not extended:
                if self._stop.is_set():
                    return  # refused because the job just finished: not a lost claim
                self.lost = True
                logger.warning("job %s: lease lost; another worker owns it now", self._job.id)
                return


def _cause(error: Exception) -> str:
    """A stable code for the logs: the domain code, or DATABASE_UNAVAILABLE for driver errors."""
    if isinstance(error, SQLAlchemyError):
        return ErrorCode.DATABASE_UNAVAILABLE.value
    return getattr(error, "cause_code", "") or type(error).__name__
