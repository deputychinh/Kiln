"""When a worker process should be replaced by a fresh one (KILN-25)."""

import resource
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from kiln_worker.enums import RecycleReason

_BYTES_PER_KIB = 1024


def peak_rss_bytes() -> int:
    """Peak resident memory of this process (`ru_maxrss` is bytes on macOS, KiB on Linux)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * _BYTES_PER_KIB


@dataclass(frozen=True, slots=True)
class RecyclePolicy:
    """Replace the process after `max_jobs` jobs or once peak memory passes `max_rss_bytes`.

    Peak memory never goes down, which is the point: Pillow keeps freed blocks mapped, so the
    peak is what the process really holds.
    """

    max_jobs: int
    max_rss_bytes: int
    rss: Callable[[], int] = field(default=peak_rss_bytes)

    def reason(self, jobs_done: int) -> RecycleReason | None:
        """Why the process should be replaced now, or None to keep going."""
        if jobs_done >= self.max_jobs:
            return RecycleReason.MAX_JOBS
        if self.rss() > self.max_rss_bytes:
            return RecycleReason.MAX_MEMORY
        return None
