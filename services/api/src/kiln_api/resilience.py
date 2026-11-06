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
from datetime import datetime
from typing import IO

from kiln_api.enums import CircuitState, PromotionResult
from kiln_api.errors import StorageUnavailableError
from kiln_api.ports import ObjectStorage, SignedPost, StoredObject

logger = logging.getLogger("kiln_api")

_BULKHEAD_RETRY_AFTER_SECONDS = 1


class CircuitBreaker:
    """Closed → open after `failures` consecutive failures → half-open after `cooldown` seconds.

    Half-open lets one trial call through at a time: success closes the circuit, failure opens it
    again for another cool-down. Thread-safe; time comes from a monotonic clock.
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
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._trial_running = False

    @property
    def state(self) -> CircuitState:
        """The current state (half-open once the cool-down has passed)."""
        with self._lock:
            return self._current_state()

    def acquire(self) -> None:
        """Allow a call, or raise `StorageUnavailableError` at once while the circuit is open."""
        with self._lock:
            state = self._current_state()
            if state is CircuitState.CLOSED:
                return
            if state is CircuitState.HALF_OPEN and not self._trial_running:
                self._trial_running = True
                return
            remaining = max(self._cooldown - (self._monotonic() - self._opened_at), 0.0)
        raise StorageUnavailableError(
            cause_code="CIRCUIT_OPEN", retry_after_seconds=max(math.ceil(remaining), 1)
        )

    def record_success(self) -> None:
        """A call got an answer from storage."""
        with self._lock:
            was_open = self._state is CircuitState.OPEN
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._trial_running = False
        if was_open:
            logger.info("storage circuit closed: storage answers again")

    def record_failure(self, cause: str) -> None:
        """A call failed because storage did not answer properly."""
        with self._lock:
            self._consecutive_failures += 1
            reopen = self._state is CircuitState.OPEN  # a failed trial
            opening = not reopen and self._consecutive_failures >= self._threshold
            if reopen or opening:
                self._state = CircuitState.OPEN
                self._opened_at = self._monotonic()
            self._trial_running = False
        if opening:
            logger.warning(
                "storage circuit opened after %d consecutive failures (cause %s);"
                " failing fast for %.0f s",
                self._threshold,
                cause,
                self._cooldown,
            )

    def release_trial(self) -> None:
        """A call ended without a verdict on storage (rejected by the bulkhead, or stopped)."""
        with self._lock:
            self._trial_running = False

    def _current_state(self) -> CircuitState:
        if self._state is CircuitState.OPEN and (
            self._monotonic() - self._opened_at >= self._cooldown
        ):
            return CircuitState.HALF_OPEN
        return self._state


class GuardedStorage:
    """`ObjectStorage` with the breaker and a bulkhead around every network call.

    Signing URLs is local (no network) and passes straight through.
    """

    def __init__(
        self,
        inner: ObjectStorage,
        breaker: CircuitBreaker,
        *,
        max_concurrent: int,
        wait_seconds: float,
    ) -> None:
        """Wrap `inner`; at most `max_concurrent` calls run at once, others wait `wait_seconds`."""
        self._inner = inner
        self._breaker = breaker
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._wait_seconds = wait_seconds

    @contextmanager
    def _call(self) -> Iterator[None]:
        """One guarded storage call: circuit first, then a bulkhead slot, then the verdict."""
        self._breaker.acquire()
        if not self._slots.acquire(timeout=self._wait_seconds):
            self._breaker.release_trial()  # storage was never asked
            raise StorageUnavailableError(
                cause_code="BULKHEAD_FULL", retry_after_seconds=_BULKHEAD_RETRY_AFTER_SECONDS
            )
        try:
            yield
        except StorageUnavailableError as error:
            self._breaker.record_failure(error.cause_code or type(error).__name__)
            raise
        except BaseException:
            self._breaker.release_trial()  # not a storage failure (a bug, or a stopped listing)
            raise
        else:
            self._breaker.record_success()
        finally:
            self._slots.release()

    def _guarded[T](self, call: Callable[[], T]) -> T:
        with self._call():
            return call()

    def ensure_bucket(self) -> None:
        """See `ObjectStorage.ensure_bucket`."""
        self._guarded(self._inner.ensure_bucket)

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
        """See `ObjectStorage.ping`; an open circuit makes readiness fail at once."""
        self._guarded(self._inner.ping)

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

    def iter_keys(self, prefix: str, *, older_than: datetime) -> Generator[str]:
        """See `ObjectStorage.iter_keys`; the listing holds one slot while it is being read."""
        with self._call():
            yield from self._inner.iter_keys(prefix, older_than=older_than)
