"""The worker process: what a spawned child runs (KILN-25).

Kept out of `__main__` so `spawn` children can import it by name: run as `python -m kiln_worker`,
`__main__` is not importable from the child.
"""

import logging
import signal
import sys
import threading
from datetime import timedelta

from kiln_api.config import Settings
from kiln_api.container import build_engine, build_storage, guard_storage
from kiln_worker.config import WorkerSettings
from kiln_worker.constants import WORKER_RECYCLE_EXIT_CODE
from kiln_worker.enums import RunEnd
from kiln_worker.recycle import RecyclePolicy
from kiln_worker.runner import build_worker

logger = logging.getLogger("kiln_worker")

_BYTES_PER_MB = 1024 * 1024


def stop_on_signals(halt: threading.Event) -> None:
    """SIGTERM and SIGINT ask the loop to stop after the current job."""
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: halt.set())


def run_worker(
    settings: Settings,
    options: WorkerSettings,
    stop: threading.Event,
) -> int:
    """The child's work: run until `stop` (exit 0) or until it should be recycled (exit 75)."""
    engine = build_engine(settings)
    worker = build_worker(
        engine,
        storage=guard_storage(build_storage(settings), settings),
        maintenance_interval=timedelta(seconds=options.maintenance_interval_seconds),
    )
    policy = RecyclePolicy(
        max_jobs=options.worker_max_jobs, max_rss_bytes=options.worker_max_rss_mb * _BYTES_PER_MB
    )
    logger.info("worker started; polling every %.1f s", options.poll_interval_seconds)
    try:
        end = worker.run(stop=stop, idle_seconds=options.poll_interval_seconds, recycle=policy)
    finally:
        engine.dispose()
    logger.info("worker stopped (%s)", end.value)
    return WORKER_RECYCLE_EXIT_CODE if end is RunEnd.RECYCLE else 0


def child_main(settings: Settings, options: WorkerSettings) -> None:
    """Body of a spawned worker process."""
    logging.basicConfig(level=options.log_level)
    halt = threading.Event()
    stop_on_signals(halt)
    sys.exit(run_worker(settings, options, halt))
