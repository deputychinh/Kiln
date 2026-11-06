"""Child bodies for sandbox tests: importable by a `spawn` child (they must live in a module)."""

import os
import resource
import signal
import time
from pathlib import Path


def sleep_forever(source: str, target: str) -> None:
    """Write the child's pid next to the target, then never finish."""
    del source
    Path(target).with_suffix(".pid").write_text(str(os.getpid()))
    time.sleep(3600)


def kill_self(source: str, target: str) -> None:
    """Die the way the OOM killer kills."""
    del source, target
    os.kill(os.getpid(), signal.SIGKILL)


def exit_without_writing(source: str, target: str) -> None:
    """Succeed without producing a preview."""
    del source, target


def report_limits(source: str, target: str) -> None:
    """Write the CPU and address-space limits the child runs under."""
    del source
    cpu = resource.getrlimit(resource.RLIMIT_CPU)[0]
    memory = resource.getrlimit(resource.RLIMIT_AS)[0]
    Path(target).write_text(f"{cpu} {memory}")


def exceed_cpu(source: str, target: str) -> None:
    """Die the way the CPU-time limit kills."""
    del source, target
    os.kill(os.getpid(), signal.SIGXCPU)
