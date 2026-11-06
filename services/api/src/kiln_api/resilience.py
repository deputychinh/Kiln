"""Stability patterns around object storage (KILN-23): a circuit breaker and a bulkhead.

Nygard, Release It! ch. 5: once storage is clearly down, fail fast instead of tying up a thread
for the full connect and read timeouts; and never let more than a fixed number of threads wait
on storage at once, so requests that do not need it stay fast.
"""

import logging
import math
import threading
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import IO

from kiln_api.enums import CircuitState, FastFailCause, PromotionResult
from kiln_api.errors import StorageUnavailableError
from kiln_api.ports import ObjectStorage, SignedPost, StoredObject

logger = logging.getLogger("kiln_api")

_BULKHEAD_RETRY_AFTER_SECONDS = 1
_SATURATION_WARNING_EVERY_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class Ticket:
    """Permission for one call: whether it is the half-open trial, and in which generation.

    The generation changes every time the circuit opens or closes, so the verdict of a call that
    started in an earlier generation (say, a slow call from before the outage) is ignored.
    """

    generation: int
    is_trial: bool


class CircuitBreaker:
    """Closed → open after `failures` consecutive failures → half-open after `cooldown` seconds.

    Half-open lets one trial call through at a time: its success closes the circuit, its failure
    opens it again for another cool-down. Thread-safe; time comes from a monotonic clock.
    """

    def __init__(
        self,
        *,
        failures: int,
        cooldown: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Open after `failures` consecutive failures, for `cooldown` seconds."""
        self._threshold = failures
        self._cooldown = cooldown
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._generation = 0
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._trial_running = False

    @property
    def state(self) -> CircuitState:
        """The current state (half-open once the cool-down has passed)."""
        with self._lock:
            return self._current_state()

    @property
    def cooldown_seconds(self) -> int:
        """The full cool-down, as whole seconds for `Retry-After`."""
        return max(math.ceil(self._cooldown), 1)

    def acquire(self) -> Ticket:
        """Allow a call, or raise `StorageUnavailableError` at once while the circuit is open."""
        with self._lock:
            state = self._current_state()
            if state is CircuitState.CLOSED:
                return Ticket(generation=self._generation, is_trial=False)
            if state is CircuitState.HALF_OPEN and not self._trial_running:
                self._trial_running = True
                return Ticket(generation=self._generation, is_trial=True)
            remaining = max(self._cooldown - (self._monotonic() - self._opened_at), 0.0)
        raise StorageUnavailableError(
            cause_code=FastFailCause.CIRCUIT_OPEN,
            retry_after_seconds=max(math.ceil(remaining), 1),
        )

    def record_success(self, ticket: Ticket) -> None:
        """The call holding `ticket` got an answer from storage."""
        with self._lock:
            if ticket.generation != self._generation:
                return  # a verdict from before the circuit last changed
            if not ticket.is_trial:
                self._consecutive_failures = 0
                return
            self._close()
        logger.info("storage circuit closed: storage answers again")

    def record_failure(self, ticket: Ticket, cause: str) -> bool:
        """The call holding `ticket` failed because of storage; True if the circuit (re)opened."""
        with self._lock:
            if ticket.generation != self._generation:
                return False
            if ticket.is_trial:
                self._open()  # the trial failed: another cool-down, no new warning
                return True
            self._consecutive_failures += 1
            if self._consecutive_failures < self._threshold:
                return False
            self._open()
        logger.warning(
            "storage circuit opened after %d consecutive failures (cause %s);"
            " failing fast for %.0f s",
            self._threshold,
            cause,
            self._cooldown,
        )
        return True

    def release(self, ticket: Ticket) -> None:
        """The call holding `ticket` ended without a verdict on storage."""
        with self._lock:
            if ticket.is_trial and ticket.generation == self._generation:
                self._trial_running = False

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._monotonic()
        self._generation += 1
        self._trial_running = False

    def _close(self) -> None:
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._generation += 1
        self._trial_running = False

    def _current_state(self) -> CircuitState:
        if self._state is CircuitState.OPEN and (
            self._monotonic() - self._opened_at >= self._cooldown
        ):
            return CircuitState.HALF_OPEN
        return self._state


class GuardedStorage:
    """`ObjectStorage` with the breaker and a bulkhead around every network call.

    Signing URLs is local (no network) and passes straight through. Readiness probes fail fast
    while the circuit is open but never count toward opening it: they use a 1 s probe client, so
    storage that is merely slow must not open the circuit for real traffic.
    """

    def __init__(
        self,
        inner: ObjectStorage,
        breaker: CircuitBreaker,
        *,
        max_concurrent: int,
        wait_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Wrap `inner`; at most `max_concurrent` calls run at once, others wait `wait_seconds`."""
        self._inner = inner
        self._breaker = breaker
        self._max_concurrent = max_concurrent
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._wait_seconds = wait_seconds
        self._monotonic = monotonic
        self._warn_lock = threading.Lock()
        self._last_saturation_warning: float | None = None

    @contextmanager
    def _call(self, *, counts: bool = True) -> Iterator[None]:
        """One guarded storage call: circuit first, then a bulkhead slot, then the verdict."""
        ticket = self._breaker.acquire()
        if not self._slots.acquire(timeout=self._wait_seconds):
            self._breaker.release(ticket)  # storage was never asked
            self._warn_saturated()
            raise StorageUnavailableError(
                cause_code=FastFailCause.BULKHEAD_FULL,
                retry_after_seconds=_BULKHEAD_RETRY_AFTER_SECONDS,
            )
        try:
            yield
        except StorageUnavailableError as error:
            if not counts:
                self._breaker.release(ticket)
            elif self._breaker.record_failure(ticket, error.cause_code or type(error).__name__):
                error.retry_after_seconds = self._breaker.cooldown_seconds
            raise
        except BaseException:
            self._breaker.release(ticket)  # not a storage failure (a bug in the caller)
            raise
        else:
            if counts:
                self._breaker.record_success(ticket)
            else:
                self._breaker.release(ticket)
        finally:
            self._slots.release()

    def _warn_saturated(self) -> None:
        """One warning per minute at most while the bulkhead turns calls away."""
        now = self._monotonic()
        with self._warn_lock:
            if self._last_saturation_warning is not None and (
                now - self._last_saturation_warning < _SATURATION_WARNING_EVERY_SECONDS
            ):
                return
            self._last_saturation_warning = now
        logger.warning(
            "storage bulkhead full: %d calls already waiting on storage; refusing more",
            self._max_concurrent,
        )

    def _guarded[T](self, call: Callable[[], T]) -> T:
        with self._call():
            return call()

    def ensure_bucket(self) -> None:
        """See `ObjectStorage.ensure_bucket`; a start-up probe (1 s client), so never counted."""
        with self._call(counts=False):
            self._inner.ensure_bucket()

    def presign_upload(
        self, *, key: str, content_type: str, size_bytes: int, ttl_seconds: int
    ) -> SignedPost:
        """Local signing: never blocked by the circuit."""
        return self._inner.presign_upload(
            key=key, content_type=content_type, size_bytes=size_bytes, ttl_seconds=ttl_seconds
        )

    def head(self, key: str) -> StoredObject | None:
        """See `ObjectStorage.head`."""
        return self._guarded(lambda: self._inner.head(key))

    def promote(self, *, source_key: str, target_key: str, etag: str) -> PromotionResult:
        """See `ObjectStorage.promote`."""
        return self._guarded(
            lambda: self._inner.promote(source_key=source_key, target_key=target_key, etag=etag)
        )

    def ping(self) -> None:
        """See `ObjectStorage.ping`; fails fast while open, never counts toward opening."""
        with self._call(counts=False):
            self._inner.ping()

    def download(self, key: str, into: IO[bytes], *, if_match: str | None = None) -> bool:
        """See `ObjectStorage.download`."""
        return self._guarded(lambda: self._inner.download(key, into, if_match=if_match))

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        """See `ObjectStorage.upload`."""
        self._guarded(lambda: self._inner.upload(key, data, content_type))

    def presign_download(self, key: str, ttl_seconds: int) -> str:
        """Local signing: never blocked by the circuit."""
        return self._inner.presign_download(key, ttl_seconds)

    def delete(self, key: str) -> None:
        """See `ObjectStorage.delete`."""
        self._guarded(lambda: self._inner.delete(key))

    def iter_key_pages(self, prefix: str, *, older_than: datetime) -> Generator[list[str]]:
        """See `ObjectStorage.iter_key_pages`; each page fetch is one guarded call.

        No slot is held between pages, so the reader may call storage (deletes) meanwhile.
        """
        pages = self._inner.iter_key_pages(prefix, older_than=older_than)
        while True:
            with self._call():
                page = next(pages, None)
            if page is None:
                return
            yield page
