"""Model previews in a disposable child process (KILN-5).

The glTF reader and renderer bound everything we could think of; this bounds everything else.
The child gets the file on disk and limits: the parent kills it after a wall-clock limit, and
the child itself holds a CPU-time limit and stops if the worker dies, so it never outlives the
job. On Linux it also gets an address-space limit (allocations past it fail, which ends as
`MODEL_TOO_LARGE`). macOS does not enforce address-space limits, so there only time is bounded.
"""

import contextlib
import logging
import multiprocessing
import os
import resource
import shutil
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO

from kiln_worker.constants import (
    MODEL_SANDBOX_CPU_SECONDS,
    MODEL_SANDBOX_MEMORY_BYTES,
    MODEL_SANDBOX_SECONDS,
    MODEL_SANDBOX_STALE_SECONDS,
    PARENT_CHECK_SECONDS,
)
from kiln_worker.errors import ModelTooLargeError, PreviewCrashedError, UnreadableModelError
from kiln_worker.glb import read_glb
from kiln_worker.model_preview import render_model

logger = logging.getLogger("kiln_worker")

_PREFIX = "kiln-model-"
_UNREADABLE = 3
_TOO_LARGE = 4
_KILLED = -signal.SIGKILL  # our kill after the time limit, or the kernel's OOM killer
_OUT_OF_CPU = -signal.SIGXCPU  # the child's own CPU-time limit

type ChildBody = Callable[[str, str], None]


def render_glb_sandboxed(source: IO[bytes], *, seconds: float = MODEL_SANDBOX_SECONDS) -> bytes:
    """The WebP preview of a GLB read from `source`, rendered in a limited child process."""
    with tempfile.TemporaryDirectory(prefix=_PREFIX) as folder:
        model, preview = Path(folder) / "model.glb", Path(folder) / "preview.webp"
        with model.open("wb") as out:
            shutil.copyfileobj(source, out)  # streamed: the worker never holds the whole file
        run_child(model, preview, seconds=seconds)
        return preview.read_bytes()


def run_child(source: Path, target: Path, *, seconds: float, body: ChildBody | None = None) -> None:
    """Run `body` (default: render) on `source` into `target` in a child; map how it ended."""
    child = multiprocessing.get_context("spawn").Process(
        target=_child_main,
        args=(body or render_file, str(source), str(target)),
        name="kiln-model-preview",
    )
    child.start()
    child.join(seconds)
    if child.is_alive():
        child.kill()
        child.join()
        msg = f"preview took more than {seconds:.0f} s"
        raise ModelTooLargeError(msg)
    code = child.exitcode
    if code == _UNREADABLE:
        msg = "unreadable glTF"
        raise UnreadableModelError(msg)
    if code in {_TOO_LARGE, _KILLED, _OUT_OF_CPU}:
        msg = "the model needs more time or memory than a preview may use"
        raise ModelTooLargeError(msg)
    if code != 0 or not target.exists():
        msg = f"preview process exited with code {code} and no preview"
        raise PreviewCrashedError(msg)


def remove_stale_folders(*, now: float | None = None) -> int:
    """Delete model folders a killed worker left behind; called when a worker starts."""
    cutoff = (time.time() if now is None else now) - MODEL_SANDBOX_STALE_SECONDS
    removed = 0
    for folder in Path(tempfile.gettempdir()).glob(f"{_PREFIX}*"):
        with contextlib.suppress(OSError):  # another worker may be removing it at the same time
            if folder.is_dir() and folder.stat().st_mtime < cutoff:
                shutil.rmtree(folder)
                removed += 1
    return removed


def limit_child() -> None:
    """Limits the child sets on itself: CPU time everywhere, address space where enforced."""
    resource.setrlimit(
        resource.RLIMIT_CPU, (MODEL_SANDBOX_CPU_SECONDS, MODEL_SANDBOX_CPU_SECONDS + 5)
    )
    try:
        resource.setrlimit(
            resource.RLIMIT_AS, (MODEL_SANDBOX_MEMORY_BYTES, MODEL_SANDBOX_MEMORY_BYTES)
        )
    except (ValueError, OSError) as error:
        if sys.platform != "darwin":  # Linux must enforce it: say so if it cannot
            logger.warning("model preview runs without a memory limit (%s)", error)


def _watch_parent(every: float = PARENT_CHECK_SECONDS) -> None:
    """Exit at once if the worker that started this child dies.

    Unlike `process.watch_parent` (a worker finishes its job, then stops), a preview child exits
    immediately: nobody is waiting for its result any more.
    """
    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def watch() -> None:
        while parent.is_alive():
            time.sleep(every)
        os._exit(_TOO_LARGE)  # nobody waits for this result any more

    threading.Thread(target=watch, name="preview-parent-watch", daemon=True).start()


def _child_main(body: ChildBody, source: str, target: str) -> None:
    limit_child()
    _watch_parent()
    body(source, target)


def render_file(source: str, target: str) -> None:
    """The default child body: read, render, write; the exit code tells the parent what happened."""
    try:
        preview = render_model(read_glb(Path(source).read_bytes()))
    except UnreadableModelError:
        sys.exit(_UNREADABLE)
    except (ModelTooLargeError, MemoryError):
        sys.exit(_TOO_LARGE)
    Path(target).write_bytes(preview)
