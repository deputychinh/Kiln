import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from kiln_api.domain.jobs import new_job
from kiln_api.enums import JobKind
from kiln_api.errors import DatabaseUnavailableError
from kiln_worker.heartbeat import LeaseHeartbeat, LeaseTiming

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
FAST = LeaseTiming(lease=timedelta(seconds=3), heartbeat_seconds=0.01, max_runtime_seconds=60)


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

    assert 1 <= len(queue.calls) <= 6
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
