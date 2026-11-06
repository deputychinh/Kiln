import logging
import multiprocessing
import signal
import threading
import time
from collections.abc import Iterator

import pytest
from process_helpers import hold_the_gil_in_a_job

from kiln_worker.constants import WORKER_OVERRAN_EXIT_CODE, WORKER_RECYCLE_EXIT_CODE
from kiln_worker.supervisor import Child, Supervisor
from kiln_worker.watchdog import JobBeacon


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
        if self.code is None:
            time.sleep(min(timeout or 0.0, 0.005))  # like a process: waiting takes time

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
    """KILN-28 AC4: the supervisor never hangs on a child that ignores its stop."""
    stop = threading.Event()
    child = _Child(None)
    child.ignores_terminate = True
    ticks = iter(range(1_000_000))

    def start() -> Child:
        threading.Timer(0.05, stop.set).start()
        return child

    with caplog.at_level(logging.ERROR, logger="kiln_worker"):
        Supervisor(
            start, stop, poll_seconds=0.01, stop_grace_seconds=60, monotonic=lambda: next(ticks)
        ).run()

    assert child.terminated
    assert child.killed
    assert "worker still running 70 s after the stop; killing it" in caplog.text


def test_a_frozen_child_asked_to_stop_is_killed_on_lost_liveness_not_after_its_grace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """While the supervisor waits for a stop, a freeze must still not outlive the lease."""
    stop = threading.Event()
    beacon = _beacon(started_ago=None)
    child = _Child(None)
    child.ignores_terminate = True

    def start() -> Child:
        now = time.monotonic()
        beacon.started("job-9", now - 70)
        beacon.alive(now - 61)  # frozen a minute ago
        stop.set()
        return child

    begun = time.monotonic()
    with caplog.at_level(logging.ERROR, logger="kiln_worker"):
        Supervisor(start, stop, poll_seconds=0.01, job_beacon=beacon, stop_grace_seconds=60).run()

    assert child.killed
    assert time.monotonic() - begun < 5  # not the 70 s grace + margin
    assert "showed no sign of life for 61 s in job job-9" in caplog.text


def test_a_child_that_ends_within_the_grace_is_not_killed() -> None:
    stop = threading.Event()
    child = _Child(None)

    def start() -> Child:
        threading.Timer(0.05, stop.set).start()
        return child

    Supervisor(start, stop, poll_seconds=0.01).run()

    assert child.terminated
    assert not child.killed


def _beacon(*, started_ago: float | None, alive_ago: float = 0.0) -> JobBeacon:
    beacon = JobBeacon(multiprocessing.get_context("spawn"))
    if started_ago is not None:
        now = time.monotonic()
        beacon.started("job-1", now - started_ago)
        beacon.alive(now - alive_ago)
    return beacon


def _run_with(
    beacon: JobBeacon,
    child: _Child,
    *,
    max_runtime_seconds: float = 1_800,
) -> list[_Child]:
    """Supervise `child` (then a healthy one until stopped); the beacon is set once it starts."""
    stop = threading.Event()
    started: list[_Child] = []
    reading = beacon.read()

    def start() -> Child:
        if started:
            threading.Timer(0.05, stop.set).start()
            started.append(_Child(None))
            return started[-1]
        if reading.started > 0:  # the supervisor clears the beacon before each start
            beacon.started(reading.job_id, reading.started)
            beacon.alive(reading.alive)
        started.append(child)
        threading.Timer(0.2, stop.set).start()
        return child

    Supervisor(
        start, stop, poll_seconds=0.01, job_beacon=beacon, max_runtime_seconds=max_runtime_seconds
    ).run()
    return started


def test_a_child_in_a_job_past_its_deadline_is_killed_and_replaced_at_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stuck = _Child(None)

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        started = _run_with(_beacon(started_ago=61), stuck, max_runtime_seconds=55)

    assert stuck.killed
    assert len(started) == 2  # replaced without a crash backoff
    assert "worker still in job job-1 after 61 s" in caplog.text
    assert "stuck worker killed; starting a fresh one" in caplog.text


def test_a_child_that_shows_no_sign_of_life_is_killed_long_before_its_deadline(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """KILN-28: a GIL hold or a freeze stops the heartbeat too; the lease must not lapse first."""
    stuck = _Child(None)

    with caplog.at_level(logging.ERROR, logger="kiln_worker"):
        _run_with(_beacon(started_ago=70, alive_ago=61), stuck, max_runtime_seconds=1_800)

    assert stuck.killed
    assert "showed no sign of life for 61 s in job job-1" in caplog.text


@pytest.mark.parametrize(
    ("started_ago", "alive_ago"),
    [(None, 0.0), (1_000.0, 0.0), (10.0, 30.0), (10.0, 100.0)],  # last: a new job, old life
)
def test_an_idle_child_or_a_live_job_in_time_is_never_killed(
    started_ago: float | None, alive_ago: float
) -> None:
    child = _Child(None)

    _run_with(_beacon(started_ago=started_ago, alive_ago=alive_ago), child)

    assert not child.killed


def test_the_beacon_is_cleared_before_each_child_starts() -> None:
    beacon = _beacon(started_ago=5_000, alive_ago=5_000)  # left by a killed child
    stop = threading.Event()

    def start() -> Child:
        assert beacon.read().started == 0.0
        threading.Timer(0.05, stop.set).start()
        return _Child(None)

    Supervisor(start, stop, poll_seconds=0.01, job_beacon=beacon).run()


def test_a_real_child_holding_the_gil_is_killed_on_lost_liveness() -> None:
    """The real thing: a spawned child stuck in libc with the GIL held, a budget far away."""
    context = multiprocessing.get_context("spawn")
    beacon = JobBeacon(context)
    stop = threading.Event()
    children: list[Child] = []

    def start() -> Child:
        if children:
            stop.set()  # one is enough
            return _Child(0)
        child = context.Process(target=hold_the_gil_in_a_job, args=(beacon,))
        child.start()
        children.append(child)
        return child

    started = time.monotonic()
    Supervisor(
        start,
        stop,
        poll_seconds=0.05,
        job_beacon=beacon,
        max_runtime_seconds=3_600,  # far beyond the test: only liveness can end it
        liveness_seconds=1,
    ).run()

    assert children[0].exitcode == -signal.SIGKILL
    assert time.monotonic() - started < 20  # not the 60 s sleep


def test_a_killed_child_that_cannot_die_does_not_hang_the_supervisor(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process in uninterruptible sleep ignores SIGKILL until the kernel lets it go."""
    monkeypatch.setattr("kiln_worker.supervisor.SUPERVISOR_REAP_SECONDS", 0.05)
    undying = _Child(None)
    undying.kill = lambda: setattr(undying, "killed", True)  # type: ignore[method-assign]

    with caplog.at_level(logging.ERROR, logger="kiln_worker"):
        _run_with(_beacon(started_ago=70, alive_ago=61), undying)

    assert undying.killed
    assert undying.join_timeouts[-1] == 0.05  # the reap is bounded, never join(None)
    assert "killed worker not gone after 0 s; moving on" in caplog.text
