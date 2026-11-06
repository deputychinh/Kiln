"""Entry point: `python -m kiln_worker` (or `make worker`)."""

import logging
import signal
import threading
from datetime import timedelta

from kiln_api.config import Settings
from kiln_api.container import build_engine, build_storage, guard_storage
from kiln_worker.config import WorkerSettings
from kiln_worker.runner import build_worker

logger = logging.getLogger("kiln_worker")


def main(
    settings: Settings | None = None,
    worker_settings: WorkerSettings | None = None,
    stop: threading.Event | None = None,
) -> int:
    """Run the worker until SIGTERM/SIGINT (or `stop`), finishing the current job first."""
    resolved = settings or Settings()
    options = worker_settings or WorkerSettings()
    logging.basicConfig(level=options.log_level)
    halt = stop or threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: halt.set())
    engine = build_engine(resolved)
    worker = build_worker(
        engine,
        storage=guard_storage(build_storage(resolved), resolved),
        maintenance_interval=timedelta(seconds=options.maintenance_interval_seconds),
    )
    logger.info("worker started; polling every %.1f s", options.poll_interval_seconds)
    try:
        worker.run(stop=halt, idle_seconds=options.poll_interval_seconds)
    finally:
        engine.dispose()
    logger.info("worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
