"""Targets for processes that tests spawn (spawn imports them by module name)."""

import ctypes
import time

from kiln_worker.watchdog import JobBeacon


def hold_the_gil_in_a_job(beacon: JobBeacon) -> None:
    """A worker child that starts a job, shows life once, then sticks in native code with the GIL.

    No thread of this process can run again, the lease heartbeat included (KILN-28).
    """
    beacon.started("0190f1c2-0000-7000-8000-00000000dead", time.monotonic())
    beacon.alive(time.monotonic())
    ctypes.PyDLL(None).sleep(60)  # libc sleep called with the GIL held
