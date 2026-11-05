import logging
import signal
import threading

import pytest

from kiln_api.config import Settings
from kiln_api.enums import Environment
from kiln_worker.__main__ import main
from kiln_worker.config import WorkerSettings


def test_the_worker_starts_polls_and_stops_cleanly(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    stop = threading.Event()
    stop.set()

    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        code = main(
            Settings(env=Environment.TEST, database_url=database_url),
            WorkerSettings(log_level="INFO", poll_interval_seconds=0.01),
            stop,
        )

    assert code == 0
    assert "worker started" in caplog.text
    assert "worker stopped" in caplog.text


def test_sigterm_asks_the_loop_to_stop(database_url: str) -> None:
    stop = threading.Event()
    timer = threading.Timer(0.2, lambda: signal.raise_signal(signal.SIGTERM))
    timer.start()

    code = main(
        Settings(env=Environment.TEST, database_url=database_url),
        WorkerSettings(poll_interval_seconds=0.05),
        stop,
    )
    timer.join()

    assert code == 0
    assert stop.is_set()
