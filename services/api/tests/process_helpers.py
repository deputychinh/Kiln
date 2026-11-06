"""Targets for processes that tests spawn (spawn imports them by module name)."""

import ctypes
import time
from typing import Any


def hold_the_gil_in_a_job(beacon: Any) -> None:
    """A worker child stuck in native code that never releases the GIL (KILN-28)."""
    beacon.value = time.monotonic()
    ctypes.PyDLL(None).sleep(60)  # libc sleep called with the GIL held: no thread can run
