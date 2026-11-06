"""Keeps one worker process running and replaces it when it recycles or crashes (KILN-25)."""

import logging
import threading
from collections.abc import Callable
from typing import Protocol

from kiln_worker.constants import (
    SUPERVISOR_POLL_SECONDS,
    WORKER_RECYCLE_EXIT_CODE,
    WORKER_RESTART_BACKOFF_MAX_SECONDS,
)

logger = logging.getLogger("kiln_worker")


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
        """Send SIGTERM: the worker finishes its current job, then exits."""
        ...


class Supervisor:
    """Runs one child at a time until `stop`.

    Recycled children are replaced at once, crashed ones after a growing backoff (1, 2, 4 … s,
    at most 30 s).
    """

    def __init__(
        self,
        start_child: Callable[[], Child],
        stop: threading.Event,
        *,
        poll_seconds: float = SUPERVISOR_POLL_SECONDS,
    ) -> None:
        """`start_child` starts a worker process and returns it."""
        self._start_child = start_child
        self._stop = stop
        self._poll_seconds = poll_seconds

    def run(self) -> int:
        """Supervise until asked to stop; returns the process exit code (0)."""
        crashes = 0
        while not self._stop.is_set():
            child = self._start_child()
            code = self._wait(child)
            if code is None:  # stop was asked while the child ran
                logger.info("stopping: waiting for the worker to finish its current job")
                child.terminate()
                child.join()
                break
            if code == WORKER_RECYCLE_EXIT_CODE:
                crashes = 0
                logger.info("worker recycled; starting a fresh one")
                continue
            if code == 0:
                break  # the child was stopped directly (a signal to the process group)
            crashes += 1
            delay = min(2 ** (crashes - 1), WORKER_RESTART_BACKOFF_MAX_SECONDS)
            logger.error("worker exited with code %d; restarting in %.0f s", code, delay)
            self._stop.wait(delay)
        logger.info("supervisor stopped")
        return 0

    def _wait(self, child: Child) -> int | None:
        """The child's exit code, or None if stop was asked first."""
        while not self._stop.is_set():
            child.join(self._poll_seconds)
            if child.exitcode is not None:
                return child.exitcode
        return None
