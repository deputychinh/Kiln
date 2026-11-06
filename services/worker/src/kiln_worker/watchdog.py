"""Job watchdog (KILN-28): a job that hangs costs its worker at most the job's time budget.

The heartbeat (KILN-24) stops extending a lease after the maximum runtime, so another worker can
retry the job; this watchdog ends the process running it at that moment, before the lease can
expire, so the job never runs twice at once. The supervisor (KILN-25) starts a fresh process.
`os._exit` ends the process while its main thread waits in native code that releases the GIL
(I/O, sockets, sleeps); the database rolls back the dropped connection and the model sandbox
child exits with its parent. Native code that holds the GIL also stops this thread, so the job's
start time is published in `beacon` and the supervisor kills the process from outside a few
seconds after the same deadline.
"""

import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Protocol

from kiln_api.constants import JOB_MAX_RUNTIME_SECONDS
from kiln_api.domain.jobs import Job
from kiln_worker.constants import (
    JOB_STOP_GRACE_SECONDS,
    WATCHDOG_POLL_SECONDS,
    WORKER_OVERRAN_EXIT_CODE,
)

logger = logging.getLogger("kiln_worker")


class JobBeacon(Protocol):
    """Shared with the supervisor: when the running job started (`time.monotonic`), 0 if idle.

    A `multiprocessing.Value("d")` across processes: CLOCK_MONOTONIC is system-wide.
    """

    value: float


class JobWatchdog:
    """Ends the process when a watched job runs past its budget, or past the grace after a stop."""

    def __init__(  # noqa: PLR0913 - every collaborator is injectable for tests
        self,
        *,
        stop: threading.Event,
        max_runtime_seconds: float = JOB_MAX_RUNTIME_SECONDS,
        stop_grace_seconds: float = JOB_STOP_GRACE_SECONDS,
        exit: Callable[[int], object] = os._exit,
        monotonic: Callable[[], float] = time.monotonic,
        poll_seconds: float = WATCHDOG_POLL_SECONDS,
        beacon: JobBeacon | None = None,
    ) -> None:
        """Watch jobs of a worker whose stop request is `stop`."""
        self._stop = stop
        self._max_runtime = max_runtime_seconds
        self._grace = stop_grace_seconds
        self._exit = exit
        self._monotonic = monotonic
        self._poll = poll_seconds
        self._beacon = beacon

    @property
    def max_runtime_seconds(self) -> float:
        """A job's budget; the process ends when a job reaches it."""
        return self._max_runtime

    @contextmanager
    def watch(self, job: Job) -> Iterator[None]:
        """Watch `job` while the block runs; nothing is watched once it ends."""
        done = threading.Event()
        thread = threading.Thread(
            target=self._guard, args=(job, done), name=f"job-watchdog-{job.id}", daemon=True
        )
        if self._beacon is not None:
            self._beacon.value = time.monotonic()
        thread.start()
        try:
            yield
        finally:
            done.set()
            if self._beacon is not None:
                self._beacon.value = 0.0
            thread.join()

    def _guard(self, job: Job, done: threading.Event) -> None:
        started = self._monotonic()
        stop_seen: float | None = None
        while not done.wait(self._poll):
            now = self._monotonic()
            if now - started >= self._max_runtime:
                self._end(
                    job,
                    done,
                    f"ran {now - started:.1f} s, past its {self._max_runtime:.1f} s budget",
                )
                return
            if self._stop.is_set():
                stop_seen = now if stop_seen is None else stop_seen
                if now - stop_seen >= self._grace:
                    self._end(
                        job, done, f"did not finish within the {self._grace:.1f} s stop grace"
                    )
                    return

    def _end(self, job: Job, done: threading.Event, why: str) -> None:
        if done.is_set():
            return  # the job finished at the last moment: nothing to end
        logger.error(
            "job %s for version %s %s (attempt %d); ending this worker process",
            job.id,
            job.version_id,
            why,
            job.attempts,
        )
        self._exit(WORKER_OVERRAN_EXIT_CODE)
