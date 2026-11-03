"""Entry point: `python -m kiln_worker`."""

import logging

from kiln_worker.config import WorkerSettings

logger = logging.getLogger("kiln_worker")


def main(settings: WorkerSettings | None = None) -> int:
    """Start the worker; job processors are registered from v0.1 (KILN-4)."""
    resolved = settings or WorkerSettings()
    logging.basicConfig(level=resolved.log_level)
    logger.info("worker started; no job kinds registered yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
