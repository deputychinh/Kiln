import logging
import threading
from collections.abc import Iterator

import pytest

from kiln_worker.constants import WORKER_OVERRAN_EXIT_CODE, WORKER_RECYCLE_EXIT_CODE
from kiln_worker.supervisor import Child, Supervisor


class _Child:
    """A fake process that exits with `code` (None: runs until terminated)."""

    def __init__(self, code: int | None) -> None:
        self.code = code
        self.terminated = False
        self.joined = False
        self.killed = False
        self.ignores_terminate = False
        self.join_timeouts: list[float | None] = []

    @property
    def exitcode(self) -> int | None:
        return self.code

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)
        self.joined = True

    def terminate(self) -> None:
        self.terminated = True
        if not self.ignores_terminate:
            self.code = 0

    def kill(self) -> None:
        self.killed = True
        self.code = -9


def _children(*codes: int | None) -> Iterator[_Child]:
    yield from (_Child(code) for code in codes)


def test_recycled_workers_are_replaced_at_once_and_a_stop_ends_the_last_one(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = threading.Event()
    started: list[_Child] = []
    supply = _children(WORKER_RECYCLE_EXIT_CODE, WORKER_RECYCLE_EXIT_CODE, None)

    def start() -> Child:
        child = next(supply)
        started.append(child)
        if child.code is None:
            threading.Timer(0.05, stop.set).start()  # stop while the third one runs
        return child

    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        assert Supervisor(start, stop, poll_seconds=0.01).run() == 0

    assert len(started) == 3
    assert started[2].terminated
    assert started[2].joined
    assert caplog.text.count("worker recycled; starting a fresh one") == 2


def _no_wait(stop: threading.Event, waits: list[float], monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_wait(timeout: float | None = None) -> bool:
        waits.append(round(timeout or 0, 3))
        return stop.is_set()

    monkeypatch.setattr(stop, "wait", fake_wait)


def test_a_crashing_worker_is_restarted_with_a_growing_backoff(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    stop = threading.Event()
    waits: list[float] = []
    _no_wait(stop, waits, monkeypatch)
    codes = iter([1, -9, 1, 1, 1, 1, 1, WORKER_RECYCLE_EXIT_CODE, 1])

    def start() -> Child:
        code = next(codes, None)
        if code is None:
            stop.set()
            return _Child(0)
        return _Child(code)

    with caplog.at_level(logging.ERROR, logger="kiln_worker"):
        Supervisor(start, stop, poll_seconds=0.01, jitter=lambda: 0.0).run()

    assert waits == [1, 2, 4, 8, 16, 30, 30, 1]  # capped at 30 s; a recycle resets it
    assert "worker exited with code -9; restarting in 2 s" in caplog.text


def test_restart_delays_get_up_to_a_quarter_of_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = threading.Event()
    waits: list[float] = []
    _no_wait(stop, waits, monkeypatch)
    codes = iter([1, 1])

    def start() -> Child:
        code = next(codes, None)
        if code is None:
            stop.set()
            return _Child(0)
        return _Child(code)

    Supervisor(start, stop, poll_seconds=0.01, jitter=lambda: 1.0).run()

    assert waits == [1.25, 2.5]


def test_a_minute_of_healthy_running_forgives_earlier_crashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = threading.Event()
    waits: list[float] = []
    _no_wait(stop, waits, monkeypatch)
    clock = [0.0]
    lifetimes = iter([1.0, 1.0, 120.0, 1.0])

    def start() -> Child:
        lifetime = next(lifetimes, None)
        if lifetime is None:
            stop.set()
            return _Child(0)
        clock[0] += lifetime  # the child runs this long, then crashes
        return _Child(1)

    def monotonic() -> float:
        return clock[0]

    # The clock is read before start: shift so each crash's uptime equals its lifetime.
    supervisor = Supervisor(start, stop, poll_seconds=0.01, monotonic=monotonic, jitter=lambda: 0.0)
    supervisor.run()

    assert waits == [1, 2, 1, 2]  # the third child ran 2 minutes: the backoff starts over


def test_a_worker_that_stopped_without_being_asked_is_restarted(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    stop = threading.Event()
    waits: list[float] = []
    _no_wait(stop, waits, monkeypatch)
    codes = iter([0])

    def start() -> Child:
        code = next(codes, None)
        if code is None:
            stop.set()
            return _Child(0)
        return _Child(code)

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        Supervisor(start, stop, poll_seconds=0.01, jitter=lambda: 0.0).run()

    assert waits == [1]
    assert "worker stopped although nobody asked; restarting in 1 s" in caplog.text


def test_a_child_stopped_by_the_same_signal_ends_the_supervisor(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = threading.Event()
    started: list[_Child] = []

    class _StoppedTogether(_Child):
        def join(self, timeout: float | None = None) -> None:
            super().join(timeout)
            stop.set()  # Ctrl-C reached the child and the supervisor together

    def start() -> Child:
        child = _StoppedTogether(0)
        started.append(child)
        return child

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        assert Supervisor(start, stop, poll_seconds=0.01).run() == 0

    assert len(started) == 1
    assert "nobody asked" not in caplog.text  # an asked-for stop is not reported as a crash


def test_no_child_starts_once_stop_was_asked() -> None:
    stop = threading.Event()
    stop.set()

    def start() -> Child:
        raise AssertionError("must not start")

    assert Supervisor(start, stop).run() == 0


def test_a_worker_ended_by_its_watchdog_is_replaced_at_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KILN-28: a hung job is the job's fault, not the process's: no crash backoff."""
    stop = threading.Event()
    waits: list[float] = []
    _no_wait(stop, waits, monkeypatch)
    codes = iter([1, WORKER_OVERRAN_EXIT_CODE, WORKER_OVERRAN_EXIT_CODE, 1])

    def start() -> Child:
        code = next(codes, None)
        if code is None:
            stop.set()
            return _Child(0)
        return _Child(code)

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        Supervisor(start, stop, poll_seconds=0.01, jitter=lambda: 0.0).run()

    assert waits == [1, 1]  # the overruns restart at once and reset the crash backoff
    assert caplog.text.count("worker ended by its watchdog (a job overran)") == 2


def test_a_stop_waits_the_grace_then_kills_a_child_that_will_not_end(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """KILN-28 AC4: the supervisor never hangs on a stuck child."""
    stop = threading.Event()
    child = _Child(None)
    child.ignores_terminate = True

    def start() -> Child:
        threading.Timer(0.05, stop.set).start()
        return child

    with caplog.at_level(logging.ERROR, logger="kiln_worker"):
        Supervisor(start, stop, poll_seconds=0.01, stop_grace_seconds=60).run()

    assert child.terminated
    assert 70 in child.join_timeouts  # the 60 s grace plus a 10 s margin
    assert child.killed
    assert "worker still running 70 s after the stop; killing it" in caplog.text


def test_a_child_that_ends_within_the_grace_is_not_killed() -> None:
    stop = threading.Event()
    child = _Child(None)

    def start() -> Child:
        threading.Timer(0.05, stop.set).start()
        return child

    Supervisor(start, stop, poll_seconds=0.01).run()

    assert child.terminated
    assert not child.killed
