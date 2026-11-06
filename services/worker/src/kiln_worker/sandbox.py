"""Model previews in a disposable child process (KILN-5).

The glTF reader and renderer bound everything we could think of; this bounds everything else.
The child gets the file on disk, a wall-clock limit and (on Linux) an address-space limit; a
child that runs out of either is killed and the model is too large. The worker process itself
never parses a model, so no file can hang it or blow up its memory.
"""

import contextlib
import multiprocessing
import resource
import signal
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from kiln_worker.constants import MODEL_SANDBOX_MEMORY_BYTES, MODEL_SANDBOX_SECONDS
from kiln_worker.errors import ModelTooLargeError, PreviewCrashedError, UnreadableModelError
from kiln_worker.glb import read_glb
from kiln_worker.model_preview import render_model

_UNREADABLE = 3
_TOO_LARGE = 4
_KILLED = -signal.SIGKILL  # the OOM killer, or our own kill after the time limit


def render_glb_sandboxed(data: bytes, *, seconds: float = MODEL_SANDBOX_SECONDS) -> bytes:
    """The WebP preview of a GLB, rendered in a child process with time and memory limits."""
    with TemporaryDirectory(prefix="kiln-model-") as folder:
        source, target = Path(folder) / "model.glb", Path(folder) / "preview.webp"
        source.write_bytes(data)
        run_child(source, target, seconds=seconds)
        return target.read_bytes()


def run_child(source: Path, target: Path, *, seconds: float) -> None:
    """Render `source` into `target` in a child; map how it ended to the failure reasons."""
    child = multiprocessing.get_context("spawn").Process(
        target=_render_file, args=(str(source), str(target)), name="kiln-model-preview"
    )
    child.start()
    child.join(seconds)
    if child.is_alive():
        child.kill()
        child.join()
        msg = f"preview took more than {seconds:.0f} s"
        raise ModelTooLargeError(msg)
    code = child.exitcode
    if code == 0:
        return
    if code == _UNREADABLE:
        msg = "unreadable glTF"
        raise UnreadableModelError(msg)
    if code in {_TOO_LARGE, _KILLED}:
        msg = "the model needs more time or memory than a preview may use"
        raise ModelTooLargeError(msg)
    msg = f"preview process exited with code {code}"
    raise PreviewCrashedError(msg)


def _limit_memory() -> None:
    # macOS refuses or ignores RLIMIT_AS; there the time limit alone applies.
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(
            resource.RLIMIT_AS, (MODEL_SANDBOX_MEMORY_BYTES, MODEL_SANDBOX_MEMORY_BYTES)
        )


def _render_file(source: str, target: str) -> None:
    """Body of the child: read, render, write; the exit code tells the parent what happened."""
    _limit_memory()
    try:
        preview = render_model(read_glb(Path(source).read_bytes()))
    except UnreadableModelError:
        sys.exit(_UNREADABLE)
    except (ModelTooLargeError, MemoryError):
        sys.exit(_TOO_LARGE)
    Path(target).write_bytes(preview)
