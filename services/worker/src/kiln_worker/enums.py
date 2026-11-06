"""Enumerations of the worker."""

from enum import StrEnum


class RunEnd(StrEnum):
    """Why `Worker.run` returned."""

    STOPPED = "stopped"
    RECYCLE = "recycle"


class RecycleReason(StrEnum):
    """Why a worker process asks to be replaced (KILN-25)."""

    MAX_JOBS = "max_jobs"
    MAX_MEMORY = "max_memory"
