"""Entry point: `python -m kiln_worker` (or `make worker`).

The process is a small supervisor; the work happens in a child process it replaces after a
number of jobs or once memory grows (KILN-25).
"""

import logging
import multiprocessing
import threading

from kiln_api.config import Settings
from kiln_worker.config import WorkerSettings
from kiln_worker.process import child_main, stop_on_signals
from kiln_worker.supervisor import Child, Supervisor


def main(
    settings: Settings | None = None,
    worker_settings: WorkerSettings | None = None,
    stop: threading.Event | None = None,
) -> int:
    """Supervise worker processes until SIGTERM/SIGINT (or `stop`)."""
    resolved = settings or Settings()
    options = worker_settings or WorkerSettings()
    logging.basicConfig(level=options.log_level)
    halt = stop or threading.Event()
    stop_on_signals(halt)
    context = multiprocessing.get_context("spawn")
    # When the child's running job started; the supervisor's backstop for a stuck child (KILN-28).
    beacon = context.Value("d", 0.0)

    def start_child() -> Child:
        child = context.Process(
            target=child_main, args=(resolved, options, beacon), name="kiln-worker"
        )
        child.start()
        return child

    supervisor = Supervisor(
        start_child, halt, stop_grace_seconds=options.job_stop_grace_seconds, job_beacon=beacon
    )
    return supervisor.run()


if __name__ == "__main__":
    raise SystemExit(main())
