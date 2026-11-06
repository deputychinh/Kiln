import logging
import threading
from collections.abc import Iterator

import pytest

from kiln_worker.constants import WORKER_RECYCLE_EXIT_CODE
from kiln_worker.supervisor import Child, Supervisor


class _Child:
    """A fake process that exits with `code` (None: runs until terminated)."""

    def __init__(self, code: int | None) -> None:
        self.code = code
        self.terminated = False
        self.joined = False

    @property
    def exitcode(self) -> int | None:
        return self.code

    def join(self, timeout: float | None = None) -> None:
        del timeout
        self.joined = True

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0


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


def test_a_crashing_worker_is_restarted_with_a_growing_backoff(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    stop = threading.Event()
    waits: list[float] = []

    def fake_wait(timeout: float | None = None) -> bool:
        waits.append(timeout or 0)
        return stop.is_set()

    monkeypatch.setattr(stop, "wait", fake_wait)
    codes = iter([1, -9, 1, 1, 1, 1, 1, WORKER_RECYCLE_EXIT_CODE, 1, 0])

    def start() -> Child:
        return _Child(next(codes))

    with caplog.at_level(logging.ERROR, logger="kiln_worker"):
        Supervisor(start, stop, poll_seconds=0.01).run()

    assert waits == [1, 2, 4, 8, 16, 30, 30, 1]  # capped at 30 s; a recycle resets it
    assert "worker exited with code -9; restarting in 2 s" in caplog.text


def test_a_child_stopped_directly_ends_the_supervisor() -> None:
    started: list[_Child] = []

    def start() -> Child:
        child = _Child(0)
        started.append(child)
        return child

    assert Supervisor(start, threading.Event(), poll_seconds=0.01).run() == 0
    assert len(started) == 1


def test_no_child_starts_once_stop_was_asked() -> None:
    stop = threading.Event()
    stop.set()

    def start() -> Child:
        raise AssertionError("must not start")

    assert Supervisor(start, stop).run() == 0
