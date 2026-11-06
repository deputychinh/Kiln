"""Keeps one worker process running and replaces it when it recycles or crashes (KILN-25)."""

import logging
import random
import threading
import time
from collections.abc import Callable
from typing import Protocol

from kiln_api.constants import JOB_MAX_RUNTIME_SECONDS
from kiln_worker.constants import (
    JOB_STOP_GRACE_SECONDS,
    SUPERVISOR_DEADLINE_MARGIN_SECONDS,
    SUPERVISOR_KILL_MARGIN_SECONDS,
    SUPERVISOR_LIVENESS_SECONDS,
    SUPERVISOR_POLL_SECONDS,
    SUPERVISOR_REAP_SECONDS,
    WORKER_HEALTHY_UPTIME_SECONDS,
    WORKER_OVERRAN_EXIT_CODE,
    WORKER_RECYCLE_EXIT_CODE,
    WORKER_RESTART_BACKOFF_MAX_SECONDS,
    WORKER_RESTART_JITTER,
    WORKER_STUCK_CODE,
)
from kiln_worker.watchdog import JobBeacon

logger = logging.getLogger("kiln_worker")

# Children replaced at once, without the crash backoff: recycled, or ended for a job's sake.
_REPLACED_AT_ONCE: dict[int, tuple[int, str]] = {
    WORKER_RECYCLE_EXIT_CODE: (logging.INFO, "worker recycled"),
    WORKER_OVERRAN_EXIT_CODE: (logging.WARNING, "worker ended by its watchdog (a job overran)"),
    WORKER_STUCK_CODE: (logging.WARNING, "stuck worker killed"),
}


class Child(Protocol):
    """The parts of `multiprocessing.Process` the supervisor uses."""

    @property
    def exitcode(self) -> int | None:
        """None while running."""
        ...

    def join(self, timeout: float | None = None) -> None:
        """Wait for the process to end."""
        ...

    def terminate(self) -> None:
        """Send SIGTERM: the worker finishes its current job (within its grace), then exits."""
        ...

    def kill(self) -> None:
        """Send SIGKILL: for a child that outlived its stop grace."""
        ...


class Supervisor:
    """Runs one child at a time until `stop`.

    Recycled children are replaced at once. Crashed ones — and ones that stopped although nobody
    asked — after a growing backoff (1, 2, 4 … s, at most 30 s, plus up to 25 % jitter) that a
    healthy run of a minute resets.
    """

    def __init__(  # noqa: PLR0913 - clock, jitter and timings are injectable for tests
        self,
        start_child: Callable[[], Child],
        stop: threading.Event,
        *,
        poll_seconds: float = SUPERVISOR_POLL_SECONDS,
        stop_grace_seconds: float = JOB_STOP_GRACE_SECONDS,
        job_beacon: JobBeacon | None = None,
        max_runtime_seconds: float = JOB_MAX_RUNTIME_SECONDS,
        liveness_seconds: float = SUPERVISOR_LIVENESS_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        """`start_child` starts a worker process and returns it."""
        self._start_child = start_child
        self._stop = stop
        self._poll_seconds = poll_seconds
        self._stop_timeout = stop_grace_seconds + SUPERVISOR_KILL_MARGIN_SECONDS
        self._beacon = job_beacon
        self._deadline = max_runtime_seconds + SUPERVISOR_DEADLINE_MARGIN_SECONDS
        self._liveness = liveness_seconds
        self._monotonic = monotonic
        self._jitter = jitter

    def run(self) -> int:
        """Supervise until asked to stop; returns the process exit code (0)."""
        crashes = 0
        while not self._stop.is_set():
            started = self._monotonic()
            child = self._start()
            code = self._wait(child)
            if code is None:  # stop was asked while the child ran
                self._stop_child(child)
                break
            if self._stop.is_set():
                break  # the child got the same signal (Ctrl-C reaches the process group)
            if code in _REPLACED_AT_ONCE:  # the process was fine (or the job was at fault)
                crashes = 0
                level, what = _REPLACED_AT_ONCE[code]
                logger.log(level, "%s; starting a fresh one", what)
                continue
            if self._monotonic() - started >= WORKER_HEALTHY_UPTIME_SECONDS:
                crashes = 0  # a long healthy run forgives earlier crashes
            crashes += 1
            delay = min(2 ** (crashes - 1), WORKER_RESTART_BACKOFF_MAX_SECONDS)
            delay *= 1 + WORKER_RESTART_JITTER * self._jitter()
            if code == 0:
                logger.warning("worker stopped although nobody asked; restarting in %.0f s", delay)
            else:
                logger.error("worker exited with code %d; restarting in %.0f s", code, delay)
            self._stop.wait(delay)
        logger.info("supervisor stopped")
        return 0

    def _start(self) -> Child:
        if self._beacon is not None:
            self._beacon.idle()  # a killed child may have left its last job behind
        return self._start_child()

    def _stop_child(self, child: Child) -> None:
        """Ask the child to stop; kill it if it outlives its grace (it should end itself)."""
        logger.info("stopping: waiting for the worker to finish its current job")
        child.terminate()
        deadline = self._monotonic() + self._stop_timeout
        # Keep the backstops while waiting: a frozen child must not outlive its lease.
        while child.exitcode is None and self._monotonic() < deadline:
            child.join(self._poll_seconds)
            reason = self._stuck_reason()
            if child.exitcode is None and reason is not None:
                self._kill_stuck(child, reason)
                return
        if child.exitcode is None:
            logger.error(
                "worker still running %.0f s after the stop; killing it", self._stop_timeout
            )
            self._kill(child)

    @staticmethod
    def _kill(child: Child) -> None:
        """SIGKILL, then a bounded wait: a child in uninterruptible sleep must not hang us."""
        child.kill()
        child.join(SUPERVISOR_REAP_SECONDS)
        if child.exitcode is None:
            logger.error("killed worker not gone after %.0f s; moving on", SUPERVISOR_REAP_SECONDS)

    def _wait(self, child: Child) -> int | None:
        """The child's exit code, or None if stop was asked first."""
        while not self._stop.is_set():
            child.join(self._poll_seconds)
            if child.exitcode is not None:
                return child.exitcode
            reason = self._stuck_reason()
            if reason is not None:
                return self._kill_stuck(child, reason)
        return None

    def _stuck_reason(self) -> str | None:
        """Why the child counts as stuck in its job, or None (idle, or alive and in time)."""
        if self._beacon is None:
            return None
        reading = self._beacon.read()
        if reading.started <= 0:
            return None
        now = self._monotonic()
        # Measured from the later of start and last sign of life, whatever order the stores land in.
        last_life = max(reading.alive, reading.started)
        if now - last_life >= self._liveness:
            return f"showed no sign of life for {now - last_life:.0f} s in job {reading.job_id}"
        if now - reading.started >= self._deadline:
            return f"still in job {reading.job_id} after {now - reading.started:.0f} s"
        return None

    def _kill_stuck(self, child: Child, reason: str) -> int:
        logger.error("worker %s (native code holding the GIL, or frozen); killing it", reason)
        self._kill(child)
        return WORKER_STUCK_CODE
