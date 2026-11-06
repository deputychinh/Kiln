"""The job watchdog ends a worker process stuck on a job (KILN-28)."""

import logging
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from job_builder import job

from kiln_api.constants import JOB_HEARTBEAT_SECONDS, JOB_LEASE_SECONDS, JOB_MAX_RUNTIME_SECONDS
from kiln_worker.constants import (
    SUPERVISOR_DEADLINE_MARGIN_SECONDS,
    WATCHDOG_POLL_SECONDS,
    WORKER_OVERRAN_EXIT_CODE,
)
from kiln_worker.watchdog import JobWatchdog

POLL = 0.005


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class _Exit:
    """Records the exit instead of ending the test process."""

    def __init__(self) -> None:
        self.codes: list[int] = []
        self.called = threading.Event()

    def __call__(self, code: int) -> None:
        self.codes.append(code)
        self.called.set()


def _watchdog(
    clock: _Clock, exit_: _Exit, stop: threading.Event, *, max_runtime: float = 60.0
) -> JobWatchdog:
    return JobWatchdog(
        max_runtime_seconds=max_runtime,
        stop=stop,
        stop_grace_seconds=10.0,
        exit=exit_,
        monotonic=clock,
        poll_seconds=POLL,
    )


def test_a_job_past_its_runtime_ends_the_process_with_the_overran_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock, exit_, running = _Clock(), _Exit(), job(attempts=2)

    with (
        caplog.at_level(logging.ERROR, logger="kiln_worker"),
        _watchdog(clock, exit_, threading.Event()).watch(running),
    ):
        clock.now += 59.9
        time.sleep(POLL * 5)
        assert exit_.codes == []
        clock.now += 0.1
        assert exit_.called.wait(1)

    assert exit_.codes == [WORKER_OVERRAN_EXIT_CODE]
    assert f"job {running.id} for version {running.version_id}" in caplog.text
    assert "ran 60.0 s, past its 60.0 s budget" in caplog.text
    assert "(attempt 2)" in caplog.text


def test_a_job_that_finishes_in_time_is_left_alone() -> None:
    clock, exit_ = _Clock(), _Exit()
    watchdog = _watchdog(clock, exit_, threading.Event())

    with watchdog.watch(job()):
        clock.now += 30
    clock.now += 3_600  # long after the job: nothing is watched any more
    time.sleep(POLL * 5)

    assert exit_.codes == []


def test_a_stop_gives_the_running_job_its_grace_then_ends_the_process(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock, exit_, stop = _Clock(), _Exit(), threading.Event()

    with (
        caplog.at_level(logging.WARNING, logger="kiln_worker"),
        _watchdog(clock, exit_, stop).watch(job()),
    ):
        stop.set()
        time.sleep(POLL * 5)  # the watchdog notes when the stop came
        clock.now += 9.9
        time.sleep(POLL * 5)
        assert exit_.codes == []
        clock.now += 0.1
        assert exit_.called.wait(1)

    assert exit_.codes == [WORKER_OVERRAN_EXIT_CODE]
    assert "did not finish within the 10.0 s stop grace" in caplog.text


def test_a_job_that_finishes_within_the_stop_grace_ends_normally() -> None:
    clock, exit_, stop = _Clock(), _Exit(), threading.Event()

    with _watchdog(clock, exit_, stop).watch(job()):
        stop.set()
        time.sleep(POLL * 5)
        clock.now += 5
    clock.now += 60
    time.sleep(POLL * 5)

    assert exit_.codes == []


def test_a_stop_asked_before_the_job_started_counts_from_the_job_start() -> None:
    clock, exit_, stop = _Clock(), _Exit(), threading.Event()
    stop.set()
    clock.now += 500  # the stop came long ago; the job just started

    with _watchdog(clock, exit_, stop).watch(job()):
        time.sleep(POLL * 5)
        assert exit_.codes == []
        clock.now += 10
        assert exit_.called.wait(1)


def test_a_process_blocked_in_native_code_is_ended_within_its_budget() -> None:
    """The real thing: `os._exit` ends a process whose main thread never returns."""
    script = textwrap.dedent(
        """
        import select, socket, threading
        from job_builder import job
        from kiln_worker.watchdog import JobWatchdog
        watchdog = JobWatchdog(
            max_runtime_seconds=0.3, stop=threading.Event(), stop_grace_seconds=10.0
        )
        with watchdog.watch(job()):
            left, right = socket.socketpair()
            select.select([left], [], [])  # blocks in C forever
        """
    )
    started = time.monotonic()
    result = subprocess.run(  # noqa: S603 - our own interpreter and script
        [sys.executable, "-c", script],
        capture_output=True,
        timeout=20,
        check=False,
        env=_child_env(),
    )

    assert result.returncode == WORKER_OVERRAN_EXIT_CODE, result.stderr.decode()
    assert time.monotonic() - started < 10


def _child_env() -> dict[str, str]:
    tests = str(Path(__file__).parents[2] / "api" / "tests")  # where job_builder lives
    return {**os.environ, "PYTHONPATH": os.pathsep.join([tests, os.environ.get("PYTHONPATH", "")])}


def test_a_stop_late_in_a_long_job_still_gives_it_the_whole_grace() -> None:
    """The grace counts from the stop, not from the job start (a 20-minute job gets 10 s too)."""
    clock, exit_, stop = _Clock(), _Exit(), threading.Event()

    with _watchdog(clock, exit_, stop, max_runtime=1_800).watch(job()):
        clock.now += 1_200
        time.sleep(POLL * 5)
        stop.set()
        time.sleep(POLL * 5)
        clock.now += 9.9
        time.sleep(POLL * 5)
        assert exit_.codes == []
        clock.now += 0.1
        assert exit_.called.wait(1)


def test_the_running_job_is_published_to_the_supervisor_and_cleared_after() -> None:
    class _Beacon:
        value = 0.0

    beacon = _Beacon()
    watchdog = JobWatchdog(stop=threading.Event(), beacon=beacon, poll_seconds=POLL)

    before = time.monotonic()
    with watchdog.watch(job()):
        assert beacon.value >= before
    assert beacon.value == 0.0


def test_a_job_that_finished_at_the_last_moment_is_not_ended() -> None:
    clock, exit_ = _Clock(), _Exit()
    watchdog = _watchdog(clock, exit_, threading.Event())
    finished = threading.Event()
    finished.set()

    watchdog._end(job(), finished, "ran 60.0 s, past its 60.0 s budget")

    assert exit_.codes == []


def test_every_deadline_falls_inside_the_lease_so_a_job_never_runs_twice() -> None:
    """The last heartbeat extends the lease at least to max runtime - heartbeat + lease."""
    lease_ends_no_earlier_than = JOB_MAX_RUNTIME_SECONDS - JOB_HEARTBEAT_SECONDS + JOB_LEASE_SECONDS
    in_process = JobWatchdog(stop=threading.Event()).max_runtime_seconds + WATCHDOG_POLL_SECONDS
    supervisor = JOB_MAX_RUNTIME_SECONDS + SUPERVISOR_DEADLINE_MARGIN_SECONDS

    assert JobWatchdog(stop=threading.Event()).max_runtime_seconds == JOB_MAX_RUNTIME_SECONDS
    assert in_process < lease_ends_no_earlier_than
    assert supervisor < lease_ends_no_earlier_than
