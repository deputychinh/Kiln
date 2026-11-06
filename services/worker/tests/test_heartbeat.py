import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from kiln_api.domain.jobs import new_job
from kiln_api.enums import JobKind
from kiln_api.errors import DatabaseUnavailableError
from kiln_worker.heartbeat import LeaseHeartbeat, LeaseTiming

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
FAST = LeaseTiming(lease=timedelta(seconds=3), heartbeat_seconds=0.01, max_runtime_seconds=60)


class _SlowQueue:
    """`extend` takes `seconds` and then answers `answer`."""

    def __init__(self, seconds: float, *, answer: bool = True) -> None:
        self.seconds = seconds
        self.answer = answer
        self.started = threading.Event()

    def extend(self, _job: Any, *, lease: timedelta, now: datetime | None = None) -> bool:
        del lease, now
        self.started.set()
        time.sleep(self.seconds)
        return self.answer


class _Queue:
    """Records extensions; answers from a script (True/False/exception), then True."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[timedelta, datetime | None]] = []
        self.lock = threading.Lock()

    def extend(self, _job: Any, *, lease: timedelta, now: datetime | None = None) -> bool:
        with self.lock:
            self.calls.append((lease, now))
            answer = self.answers.pop(0) if self.answers else True
        if isinstance(answer, Exception):
            raise answer
        return bool(answer)


def _job() -> Any:
    return new_job(JobKind.THUMBNAIL, uuid4(), job_id=uuid4(), now=NOW)


def _beat(queue: _Queue, timing: LeaseTiming = FAST, now: datetime | None = None) -> Any:
    return LeaseHeartbeat(queue, _job(), timing=timing, queue_now=lambda: now)  # type: ignore[arg-type]


def test_a_running_job_extends_its_lease_until_the_block_ends() -> None:
    queue = _Queue()
    heartbeat = _beat(queue, now=NOW)

    with heartbeat:
        time.sleep(0.1)
    calls_at_exit = len(queue.calls)
    time.sleep(0.05)

    assert calls_at_exit >= 3
    assert len(queue.calls) == calls_at_exit  # nothing after the block ended
    assert queue.calls[0] == (timedelta(seconds=3), NOW)
    assert not heartbeat._thread.is_alive()
    assert heartbeat.lost is False


def test_a_refused_extension_means_the_lease_is_lost_and_stops_the_heartbeat(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = _Queue(True, False)

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        heartbeat = _beat(queue)
        with heartbeat:
            time.sleep(0.1)

    assert heartbeat.lost is True
    assert len(queue.calls) == 2
    assert caplog.text.count("lease lost") == 1


def test_a_hung_job_stops_being_extended_after_the_maximum_runtime(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = _Queue()
    timing = LeaseTiming(
        lease=timedelta(seconds=3), heartbeat_seconds=0.01, max_runtime_seconds=0.05
    )

    with caplog.at_level(logging.WARNING, logger="kiln_worker"), _beat(queue, timing):
        time.sleep(0.2)

    assert len(queue.calls) <= 6  # stopped early, whatever the scheduling
    assert "no longer extending its lease" in caplog.text


def test_a_database_hiccup_is_logged_and_the_next_tick_extends_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = _Queue(DatabaseUnavailableError(), True)

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        heartbeat = _beat(queue)
        with heartbeat:
            time.sleep(0.1)

    assert "lease extension failed (DatabaseUnavailableError); retrying" in caplog.text
    assert len(queue.calls) >= 2
    assert heartbeat.lost is False


def test_leaving_the_block_waits_for_an_extension_in_flight() -> None:
    queue = _SlowQueue(0.1)
    heartbeat = _beat(queue)  # type: ignore[arg-type]

    with heartbeat:
        queue.started.wait(5)

    assert not heartbeat._thread.is_alive()


def test_waiting_for_a_stuck_extension_is_bounded_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = _SlowQueue(1.0)
    timing = LeaseTiming(
        lease=timedelta(seconds=3),
        heartbeat_seconds=0.01,
        max_runtime_seconds=60,
        join_seconds=0.05,
    )
    started = time.monotonic()

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        heartbeat = _beat(queue, timing)  # type: ignore[arg-type]
        with heartbeat:
            queue.started.wait(5)

    assert time.monotonic() - started < 0.5
    assert "still pending after 0 s; moving on" in caplog.text


def test_a_refusal_after_the_job_finished_is_not_reported_as_a_lost_claim(
    caplog: pytest.LogCaptureFixture,
) -> None:
    queue = _SlowQueue(0.05, answer=False)  # the outcome was written while this tick ran

    with caplog.at_level(logging.WARNING, logger="kiln_worker"):
        heartbeat = _beat(queue)  # type: ignore[arg-type]
        with heartbeat:
            queue.started.wait(5)

    assert heartbeat.lost is False
    assert "lease lost" not in caplog.text


def test_stopping_twice_is_harmless() -> None:
    heartbeat = _beat(_Queue())
    with heartbeat:
        heartbeat.stop()
    heartbeat.stop()


def test_database_errors_are_logged_with_a_stable_code(caplog: pytest.LogCaptureFixture) -> None:
    queue = _Queue(OperationalError("SELECT 1", {}, Exception("server closed the connection")))

    with caplog.at_level(logging.WARNING, logger="kiln_worker"), _beat(queue):
        time.sleep(0.05)

    assert "lease extension failed (DATABASE_UNAVAILABLE); retrying" in caplog.text
