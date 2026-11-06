import contextlib
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes import FakeStorage
from pydantic import ValidationError

from kiln_api.config import Settings
from kiln_api.enums import CircuitState, PromotionResult
from kiln_api.errors import StorageUnavailableError
from kiln_api.resilience import CircuitBreaker, GuardedStorage


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def ticks() -> _Clock:
    return _Clock()


@pytest.fixture
def breaker(ticks: _Clock) -> CircuitBreaker:
    return CircuitBreaker(failures=3, cooldown=30.0, monotonic=ticks)


def _state(breaker: CircuitBreaker) -> CircuitState:
    return breaker.state  # a call, so mypy does not narrow across state changes


def _fail(breaker: CircuitBreaker, times: int) -> None:
    for _ in range(times):
        ticket = breaker.acquire()
        breaker.record_failure(ticket, "ReadTimeoutError")


def test_the_circuit_opens_after_consecutive_failures_and_fails_fast_with_the_cooldown_left(
    breaker: CircuitBreaker, ticks: _Clock, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="kiln_api"):
        _fail(breaker, 3)

    assert _state(breaker) is CircuitState.OPEN
    ticks.now += 10.6
    with pytest.raises(StorageUnavailableError) as raised:
        breaker.acquire()
    assert raised.value.cause_code == "CIRCUIT_OPEN"
    assert raised.value.retry_after_seconds == 20  # ceil(19.4): never tell clients too early
    assert caplog.text.count("storage circuit opened after 3 consecutive failures") == 1
    assert "ReadTimeoutError" in caplog.text


def test_only_consecutive_failures_count(breaker: CircuitBreaker) -> None:
    _fail(breaker, 2)
    ticket = breaker.acquire()
    breaker.record_success(ticket)
    _fail(breaker, 2)

    assert _state(breaker) is CircuitState.CLOSED


def test_after_the_cooldown_one_trial_goes_through_and_success_closes(
    breaker: CircuitBreaker, ticks: _Clock, caplog: pytest.LogCaptureFixture
) -> None:
    _fail(breaker, 3)
    ticks.now += 30.0

    assert _state(breaker) is CircuitState.HALF_OPEN
    trial = breaker.acquire()
    with pytest.raises(StorageUnavailableError) as raised:
        breaker.acquire()  # everyone else still fails fast
    assert raised.value.retry_after_seconds == 1
    with caplog.at_level(logging.INFO, logger="kiln_api"):
        breaker.record_success(trial)

    assert _state(breaker) is CircuitState.CLOSED
    assert "storage circuit closed" in caplog.text
    breaker.acquire()


def test_a_failed_trial_reopens_for_a_full_cooldown_without_logging_again(
    breaker: CircuitBreaker, ticks: _Clock, caplog: pytest.LogCaptureFixture
) -> None:
    _fail(breaker, 3)
    ticks.now += 30.0
    trial = breaker.acquire()
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="kiln_api"):
        breaker.record_failure(trial, "ConnectTimeoutError")

    assert _state(breaker) is CircuitState.OPEN
    ticks.now += 29.9
    assert _state(breaker) is CircuitState.OPEN
    ticks.now += 0.1
    assert _state(breaker) is CircuitState.HALF_OPEN
    assert "opened" not in caplog.text


def test_releasing_a_trial_without_a_verdict_lets_the_next_call_try(
    breaker: CircuitBreaker, ticks: _Clock
) -> None:
    _fail(breaker, 3)
    ticks.now += 30.0
    trial = breaker.acquire()
    breaker.release(trial)

    breaker.acquire()  # a new trial is allowed
    assert _state(breaker) is CircuitState.HALF_OPEN


def _guarded(
    storage: FakeStorage, *, failures: int = 2, slots: int = 4, wait: float = 0.05
) -> tuple[GuardedStorage, CircuitBreaker]:
    breaker = CircuitBreaker(failures=failures, cooldown=30.0)
    return GuardedStorage(storage, breaker, max_concurrent=slots, wait_seconds=wait), breaker


def test_storage_failures_open_the_circuit_and_then_storage_is_not_called() -> None:
    storage = FakeStorage()
    storage.available = False
    guarded, breaker = _guarded(storage)
    calls: list[str] = []
    storage.on_head = lambda: calls.append("head")

    for _ in range(2):
        with pytest.raises(StorageUnavailableError):
            guarded.head("k")
    with pytest.raises(StorageUnavailableError) as raised:
        guarded.head("k")

    assert _state(breaker) is CircuitState.OPEN
    assert raised.value.cause_code == "CIRCUIT_OPEN"
    assert calls == []  # FakeStorage checks availability before the hook; nothing reached it


def test_answers_like_not_found_or_changed_are_successes() -> None:
    storage = FakeStorage()
    guarded, breaker = _guarded(storage, failures=1)

    assert guarded.head("missing") is None
    storage.put("src", 1, "image/png")
    assert guarded.promote(source_key="src", target_key="dst", etag='"other"') is (
        PromotionResult.CHANGED
    )
    assert _state(breaker) is CircuitState.CLOSED


def test_signing_is_local_and_never_blocked_by_an_open_circuit() -> None:
    storage = FakeStorage()
    storage.available = False
    guarded, breaker = _guarded(storage, failures=1)
    with pytest.raises(StorageUnavailableError):
        guarded.head("k")
    assert _state(breaker) is CircuitState.OPEN

    assert guarded.presign_download("thumbs/a.webp", 60).startswith("http://storage.test/")
    assert (
        guarded.presign_upload(
            key="uploads/a/b", content_type="image/png", size_bytes=1, ttl_seconds=60
        ).fields["key"]
        == "uploads/a/b"
    )


def test_every_network_call_goes_through_the_guard() -> None:
    storage = FakeStorage()
    storage.available = False
    guarded, _ = _guarded(storage, failures=100)
    calls: list[Any] = [
        guarded.ensure_bucket,
        guarded.ping,
        lambda: guarded.head("k"),
        lambda: guarded.promote(source_key="a", target_key="b", etag="e"),
        lambda: guarded.delete("k"),
        lambda: guarded.upload("k", b"x", "image/png"),
        lambda: guarded.download("k", __import__("io").BytesIO()),
        lambda: list(guarded.iter_keys("uploads/", older_than=datetime.now(UTC))),
    ]
    for call in calls:
        with pytest.raises(StorageUnavailableError):
            call()

    storage.available = True
    storage.put("uploads/x", 1, "image/png", data=b"x")
    guarded.ensure_bucket()
    guarded.ping()
    guarded.upload("k", b"x", "image/png")
    guarded.delete("k")
    assert list(guarded.iter_keys("uploads/", older_than=datetime(9999, 1, 1, tzinfo=UTC))) == [
        "uploads/x"
    ]


def test_a_full_bulkhead_rejects_after_the_wait_without_opening_the_circuit() -> None:
    storage = FakeStorage()
    guarded, breaker = _guarded(storage, failures=1, slots=1, wait=0.05)
    entered, release = threading.Event(), threading.Event()

    def slow() -> None:
        entered.set()
        release.wait(5)

    storage.on_head = slow
    holder = threading.Thread(target=lambda: guarded.head("slow"))
    holder.start()
    entered.wait(5)
    storage.on_head = None
    try:
        for _ in range(3):
            with pytest.raises(StorageUnavailableError) as raised:
                guarded.head("other")
            assert raised.value.cause_code == "BULKHEAD_FULL"
            assert raised.value.retry_after_seconds == 1
    finally:
        release.set()
        holder.join(5)

    assert _state(breaker) is CircuitState.CLOSED
    assert guarded.head("other") is None  # the slot is free again


def test_a_call_waits_for_a_slot_that_frees_up_within_the_wait() -> None:
    storage = FakeStorage()
    guarded, _ = _guarded(storage, slots=1, wait=2.0)
    entered = threading.Event()

    def briefly() -> None:
        entered.set()
        time.sleep(0.1)

    storage.on_head = briefly
    holder = threading.Thread(target=lambda: guarded.head("slow"))
    holder.start()
    entered.wait(5)
    storage.on_head = None

    assert guarded.head("other") is None  # waited about 0.1 s, then got the slot
    holder.join(5)


def test_a_trial_turned_away_by_the_bulkhead_lets_the_next_call_try() -> None:
    storage = FakeStorage()
    ticks = _Clock()
    breaker = CircuitBreaker(failures=1, cooldown=30.0, monotonic=ticks)
    guarded = GuardedStorage(storage, breaker, max_concurrent=1, wait_seconds=0.01)
    entered, release = threading.Event(), threading.Event()

    def slow() -> None:
        entered.set()
        release.wait(5)

    storage.on_head = slow
    holder = threading.Thread(target=lambda: guarded.head("slow"))  # holds the only slot
    holder.start()
    entered.wait(5)
    storage.on_head = None
    ticket = breaker.acquire()
    breaker.record_failure(ticket, "ReadTimeoutError")  # meanwhile storage failed elsewhere: open
    ticks.now += 30.0
    try:
        for _ in range(2):  # each caller gets the trial, finds no slot, and gives the trial back
            with pytest.raises(StorageUnavailableError) as raised:
                guarded.head("k")
            assert raised.value.cause_code == "BULKHEAD_FULL"
    finally:
        release.set()
        holder.join(5)


def test_verdicts_of_calls_from_an_earlier_generation_are_ignored(
    breaker: CircuitBreaker, ticks: _Clock
) -> None:
    old = breaker.acquire()  # a slow call that started while the circuit was closed
    _fail(breaker, 3)
    ticks.now += 30.0
    trial = breaker.acquire()

    breaker.release(old)  # the old call ends with a bug...
    with pytest.raises(StorageUnavailableError):
        breaker.acquire()  # ...and does not free the trial: no second trial
    breaker.record_failure(old, "ReadTimeoutError")  # a late failure does not restart the clock
    breaker.record_success(old)  # a late success does not close the circuit
    assert _state(breaker) is CircuitState.HALF_OPEN

    breaker.record_success(trial)
    assert _state(breaker) is CircuitState.CLOSED
    breaker.record_failure(trial, "x")  # the trial's ticket is stale now too
    assert _state(breaker) is CircuitState.CLOSED


def test_a_late_success_from_before_the_outage_does_not_reset_the_new_count(
    breaker: CircuitBreaker, ticks: _Clock
) -> None:
    old = breaker.acquire()  # started before the outage, answers only much later
    _fail(breaker, 3)
    ticks.now += 30.0
    breaker.record_success(breaker.acquire())  # the trial closes the circuit
    _fail(breaker, 2)

    breaker.record_success(old)  # stale: must not wipe the two new failures
    _fail(breaker, 1)

    assert _state(breaker) is CircuitState.OPEN


def test_two_trials_never_run_at_once_under_many_threads() -> None:
    storage = FakeStorage()
    ticks = _Clock()
    breaker = CircuitBreaker(failures=1, cooldown=30.0, monotonic=ticks)
    guarded = GuardedStorage(storage, breaker, max_concurrent=64, wait_seconds=1.0)
    inside: list[int] = []
    peak: list[int] = [0]
    lock = threading.Lock()

    def observe() -> None:
        with lock:
            inside.append(1)
            peak[0] = max(peak[0], len(inside))
        time.sleep(0.02)
        with lock:
            inside.pop()
        raise StorageUnavailableError(cause_code="ReadTimeoutError")  # the trial fails

    ticket = breaker.acquire()
    breaker.record_failure(ticket, "x")
    ticks.now += 30.0
    storage.on_head = observe
    barrier = threading.Barrier(32)

    def call() -> None:
        barrier.wait()
        with contextlib.suppress(StorageUnavailableError):
            guarded.head("k")

    threads = [threading.Thread(target=call) for _ in range(32)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert peak[0] == 1
    assert _state(breaker) is CircuitState.OPEN


def test_the_request_that_opens_the_circuit_already_gets_the_cooldown_as_retry_after() -> None:
    storage = FakeStorage()
    storage.available = False
    guarded, _ = _guarded(storage, failures=2)
    with pytest.raises(StorageUnavailableError) as first:
        guarded.head("k")
    with pytest.raises(StorageUnavailableError) as opening:
        guarded.head("k")

    assert first.value.retry_after_seconds is None  # the default 1 s applies
    assert opening.value.retry_after_seconds == 30


def test_readiness_probes_fail_fast_when_open_but_never_open_the_circuit() -> None:
    storage = FakeStorage()
    storage.available = False
    guarded, breaker = _guarded(storage, failures=1)
    for _ in range(5):
        with pytest.raises(StorageUnavailableError) as probe:
            guarded.ping()
        assert probe.value.cause_code != "CIRCUIT_OPEN"
    assert _state(breaker) is CircuitState.CLOSED

    with pytest.raises(StorageUnavailableError):
        guarded.head("k")  # real traffic opens it
    with pytest.raises(StorageUnavailableError) as fast:
        guarded.ping()
    assert fast.value.cause_code == "CIRCUIT_OPEN"


def test_a_successful_probe_does_not_close_an_open_circuit() -> None:
    storage = FakeStorage()
    ticks = _Clock()
    breaker = CircuitBreaker(failures=1, cooldown=30.0, monotonic=ticks)
    guarded = GuardedStorage(storage, breaker, max_concurrent=4, wait_seconds=0.01)
    ticket = breaker.acquire()
    breaker.record_failure(ticket, "x")
    ticks.now += 30.0

    guarded.ping()  # takes and gives back the trial without a verdict

    assert _state(breaker) is CircuitState.HALF_OPEN
    assert guarded.head("k") is None  # real traffic gets the trial and closes the circuit
    assert _state(breaker) is CircuitState.CLOSED


def test_a_bug_in_a_call_is_not_counted_against_storage() -> None:
    storage = FakeStorage()
    guarded, breaker = _guarded(storage, failures=1)

    def broken() -> None:
        raise KeyError("bug")

    storage.on_head = broken
    with pytest.raises(KeyError):
        guarded.head("k")

    assert _state(breaker) is CircuitState.CLOSED


def test_a_listing_failure_counts_and_a_listing_trial_closes_the_circuit() -> None:
    storage = FakeStorage()
    storage.put("uploads/a", 1, "image/png")
    storage.put("uploads/b", 1, "image/png")
    ticks = _Clock()
    breaker = CircuitBreaker(failures=1, cooldown=30.0, monotonic=ticks)
    guarded = GuardedStorage(storage, breaker, max_concurrent=1, wait_seconds=0.05)
    later = datetime(9999, 1, 1, tzinfo=UTC)
    storage.list_available = False
    with pytest.raises(StorageUnavailableError):
        list(guarded.iter_keys("uploads/", older_than=later))
    assert _state(breaker) is CircuitState.OPEN

    ticks.now += 30.0
    storage.list_available = True
    listing = guarded.iter_keys("uploads/", older_than=later)
    assert next(listing) == "uploads/a"  # the first step is the trial and succeeds
    assert _state(breaker) is CircuitState.CLOSED
    listing.close()


def test_a_reader_can_call_storage_between_listing_steps_with_a_single_slot() -> None:
    storage = FakeStorage()
    for key in ("uploads/a", "uploads/b", "uploads/c"):
        storage.put(key, 1, "image/png")
    guarded, _ = _guarded(storage, slots=1, wait=0.01)

    for key in guarded.iter_keys("uploads/", older_than=datetime(9999, 1, 1, tzinfo=UTC)):
        guarded.delete(key)  # no slot is held while the reader works

    assert storage.objects == {}


def test_stopping_a_listing_early_closes_the_underlying_listing() -> None:
    storage = FakeStorage()
    for key in ("uploads/a", "uploads/b"):
        storage.put(key, 1, "image/png")
    guarded, _ = _guarded(storage)

    listing = guarded.iter_keys("uploads/", older_than=datetime(9999, 1, 1, tzinfo=UTC))
    next(listing)
    assert storage.open_listings == 1
    listing.close()

    assert storage.listed == 1
    assert storage.open_listings == 0  # the storage-side listing was closed too


@pytest.mark.parametrize(
    "field",
    [
        "storage_breaker_failures",
        "storage_breaker_cooldown_seconds",
        "storage_max_concurrent",
        "storage_bulkhead_wait_seconds",
    ],
)
def test_resilience_settings_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: 0})
