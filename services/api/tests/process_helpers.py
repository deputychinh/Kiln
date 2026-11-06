"""Targets for processes that tests spawn (spawn imports them by module name).

Kept beside the other shared test helpers; typed by a protocol so the API's test folder never
imports the worker.
"""

import ctypes
import time
from typing import Protocol


class _Beacon(Protocol):
    """The part of the worker's `JobBeacon` a spawned test child writes."""

    def started(self, job_id: str, now: float) -> None: ...

    def alive(self, now: float) -> None: ...


def hold_the_gil_in_a_job(beacon: _Beacon) -> None:
    """A worker child that starts a job, shows life once, then sticks in native code with the GIL.

    No thread of this process can run again, the lease heartbeat included (KILN-28).
    """
    beacon.started("0190f1c2-0000-7000-8000-00000000dead", time.monotonic())
    beacon.alive(time.monotonic())
    ctypes.PyDLL(None).sleep(60)  # libc sleep called with the GIL held
