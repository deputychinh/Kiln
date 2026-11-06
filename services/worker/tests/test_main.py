import contextlib
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from kiln_api.config import Settings
from kiln_api.enums import Environment
from kiln_api.resilience import GuardedStorage
from kiln_worker.__main__ import main
from kiln_worker.config import WorkerSettings
from kiln_worker.constants import WORKER_RECYCLE_EXIT_CODE
from kiln_worker.enums import RunEnd
from kiln_worker.process import child_main, run_worker, watch_parent
from kiln_worker.runner import build_worker


@pytest.mark.usefixtures("engine")  # the loop may take a maintenance lease; clean it up
def test_the_worker_starts_polls_and_stops_cleanly(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    stop = threading.Event()
    stop.set()

    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        code = run_worker(
            Settings(env=Environment.TEST, database_url=database_url),
            WorkerSettings(log_level="INFO", poll_interval_seconds=0.01),
            stop,
        )

    assert code == 0
    assert "worker started" in caplog.text
    assert "worker stopped (stopped)" in caplog.text


@pytest.mark.usefixtures("engine")
def test_a_worker_that_should_recycle_exits_with_the_recycle_code(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("kiln_worker.runner.Worker.run", lambda *_, **__: RunEnd.RECYCLE)

    code = run_worker(
        Settings(env=Environment.TEST, database_url=database_url),
        WorkerSettings(),
        threading.Event(),
    )

    assert code == WORKER_RECYCLE_EXIT_CODE


@pytest.mark.usefixtures("engine")
def test_the_worker_guards_its_storage_and_passes_the_recycle_policy(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: dict[str, Any] = {}
    real_build = build_worker

    def spy(engine: Any, **kwargs: Any) -> Any:
        built.update(kwargs)
        worker = real_build(engine, **kwargs)
        real_run = worker.run

        def run(**run_kwargs: Any) -> Any:
            built["recycle"] = run_kwargs["recycle"]
            return real_run(**run_kwargs)

        worker.run = run  # type: ignore[method-assign]
        return worker

    monkeypatch.setattr("kiln_worker.process.build_worker", spy)
    stop = threading.Event()
    stop.set()

    run_worker(
        Settings(env=Environment.TEST, database_url=database_url),
        WorkerSettings(worker_max_jobs=7, worker_max_rss_mb=3),
        stop,
    )

    assert isinstance(built["storage"], GuardedStorage)
    assert (built["recycle"].max_jobs, built["recycle"].max_rss_bytes) == (7, 3 * 1024 * 1024)


@pytest.mark.usefixtures("engine")
def test_sigterm_stops_the_supervisor_and_its_spawned_worker(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    previous = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    stop = threading.Event()
    timer = threading.Timer(3.0, lambda: signal.raise_signal(signal.SIGTERM))
    timer.start()

    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        code = main(
            Settings(env=Environment.TEST, database_url=database_url),
            WorkerSettings(poll_interval_seconds=0.05),
            stop,
        )
    timer.join()
    for signum, handler in previous.items():
        signal.signal(signum, handler)  # leave Ctrl-C working for the rest of the run

    assert code == 0
    assert stop.is_set()
    assert "waiting for the worker to finish its current job" in caplog.text
    assert "supervisor stopped" in caplog.text


@pytest.mark.parametrize("field", ["worker_max_jobs", "worker_max_rss_mb"])
def test_recycle_settings_must_be_positive(field: str) -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        WorkerSettings.model_validate({field: 0})


def test_a_spawned_child_exits_with_the_worker_s_code(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("kiln_worker.process.run_worker", lambda *_: WORKER_RECYCLE_EXIT_CODE)
    monkeypatch.setattr("kiln_worker.process.stop_on_signals", lambda _: None)

    with pytest.raises(SystemExit) as exited:
        child_main(Settings(env=Environment.TEST, database_url=database_url), WorkerSettings())

    assert exited.value.code == WORKER_RECYCLE_EXIT_CODE


@contextmanager
def _supervisor_process(database_url: str) -> Iterator[tuple[subprocess.Popen[str], list[str]]]:
    """`python -m kiln_worker` in its own process group; the group is killed whatever happens."""
    env = {
        **os.environ,
        "KILN_ENV": "test",
        "KILN_DATABASE_URL": database_url,
        "KILN_POLL_INTERVAL_SECONDS": "0.05",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "kiln_worker"],
        env=env,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    lines: list[str] = []
    assert process.stderr is not None
    stream = process.stderr
    reader = threading.Thread(target=lambda: lines.extend(stream), daemon=True)
    reader.start()
    try:
        yield process, lines
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(10)
        reader.join(5)
        stream.close()


def _wait_for(lines: list[str], text: str, seconds: float = 30) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if any(text in line for line in lines):
            return True
        time.sleep(0.05)
    return False


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.usefixtures("engine")  # cleans the maintenance lease the child may take
def test_python_m_kiln_worker_starts_a_child_that_works_and_stops_on_sigterm(
    database_url: str,
) -> None:
    with _supervisor_process(database_url) as (supervisor, lines):
        assert _wait_for(lines, "worker started"), "".join(lines)
        supervisor.send_signal(signal.SIGTERM)
        supervisor.wait(30)
        assert _wait_for(lines, "supervisor stopped", 5), "".join(lines)

        assert supervisor.returncode == 0
        assert not any("exited with code" in line for line in lines)
        assert not _group_alive(supervisor.pid)  # no child left behind


@pytest.mark.usefixtures("engine")
def test_a_worker_whose_supervisor_dies_stops_by_itself(database_url: str) -> None:
    with _supervisor_process(database_url) as (supervisor, lines):
        assert _wait_for(lines, "worker started"), "".join(lines)

        supervisor.kill()  # SIGKILL: no chance to stop the child
        supervisor.wait(10)

        assert _wait_for(lines, "supervisor gone; stopping after the current job", 10)
        deadline = time.monotonic() + 10
        while _group_alive(supervisor.pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not _group_alive(supervisor.pid)


def test_a_child_watches_its_supervisor_and_stops_when_it_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Parent:
        alive = True

        def is_alive(self) -> bool:
            return self.alive

    parent = _Parent()
    monkeypatch.setattr("multiprocessing.parent_process", lambda: parent)
    halt = threading.Event()

    watch_parent(halt, every=0.01)
    time.sleep(0.05)
    assert not halt.is_set()
    parent.alive = False

    assert halt.wait(1)


def test_in_process_runs_have_no_supervisor_to_watch() -> None:
    halt = threading.Event()
    watch_parent(halt, every=0.01)  # no spawned parent: nothing starts

    assert not any(t.name == "parent-watch" for t in threading.enumerate())
