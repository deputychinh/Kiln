"""Re-check ready models under the worker's current rules (KILN-36): `make recheck-models`.

Versions made ready before a rule was added (KILN-9 accessor bounds, KILN-36 strict trees in every
scene) are read again with the same sandboxed reader and renderer the worker uses. One that now
fails becomes `failed` with `UNREADABLE_MODEL` or `MODEL_TOO_LARGE`, and its asset's cover falls
back to the newest other ready version. Each write is guarded by the version still being `ready`
(compare-and-set), so the command is safe to run twice, in parallel, and while workers run.
Only counts are logged: no ids, names or file contents.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from typing import IO

from sqlalchemy import Engine

from kiln_api.clock import DatabaseClock
from kiln_api.config import Settings
from kiln_api.container import build_engine, build_storage, guard_storage
from kiln_api.domain.assets import AssetVersion, transition
from kiln_api.enums import FailureReason, VersionStatus
from kiln_api.errors import InvalidStatusTransitionError, StorageUnavailableError
from kiln_api.ports import AssetRepository, Clock, MaintenanceStore, ObjectStorage, UnitOfWork
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.maintenance import SqlMaintenanceStore
from kiln_api.repositories.unit_of_work import SqlUnitOfWork
from kiln_worker.constants import MODEL_MAX_BYTES, RECHECK_BATCH_SIZE, SPOOL_MAX_BYTES
from kiln_worker.errors import ModelTooLargeError, PreviewCrashedError, UnreadableModelError
from kiln_worker.sandbox import render_glb_sandboxed

logger = logging.getLogger("kiln_worker")

type Render = Callable[[IO[bytes]], bytes]


@dataclass(frozen=True, slots=True)
class RecheckReport:
    """Counts of one run: `checked` = `kept` + `unreadable` + `too_large` + `skipped`.

    `skipped` versions stay ready: their file changed or vanished, the preview process crashed,
    or another writer changed them first. `storage_down` means the run stopped early.
    """

    checked: int = 0
    kept: int = 0
    unreadable: int = 0
    too_large: int = 0
    skipped: int = 0
    storage_down: bool = False


@dataclass(frozen=True, slots=True)
class RecheckPorts:
    """Everything the re-check talks to."""

    store: MaintenanceStore
    assets: AssetRepository
    storage: ObjectStorage
    unit_of_work: UnitOfWork


class _Skip(Exception):  # noqa: N818 - control flow, never leaves this module
    """This version cannot be judged now; it stays ready."""


class ModelRecheck:
    """Walks every ready model version once, in id order, a batch at a time."""

    def __init__(
        self,
        ports: RecheckPorts,
        clock: Clock,
        *,
        render: Render = render_glb_sandboxed,
        batch_size: int = RECHECK_BATCH_SIZE,
    ) -> None:
        """Receive the collaborators; `render` is the worker's sandboxed reader and renderer."""
        self._ports = ports
        self._clock = clock
        self._render = render
        self._batch_size = batch_size

    def run(self) -> RecheckReport:
        """Check every version that is ready when its batch is read; see the module docstring."""
        counts = Counter[str]()
        after = None
        try:
            while ids := self._ports.store.ready_model_versions(
                after=after, limit=self._batch_size
            ):
                after = ids[-1]
                versions = self._ports.assets.versions_by_id(ids)
                for version_id in ids:
                    version = versions.get(version_id)
                    if version is None or version.status is not VersionStatus.READY:
                        continue  # deleted or changed between the two reads
                    counts["checked"] += 1
                    counts[self._check(version)] += 1
        except StorageUnavailableError:
            counts["skipped"] += 1  # the version being checked when storage went away
            return _report(counts, storage_down=True)
        return _report(counts)

    def _check(self, version: AssetVersion) -> str:
        """Which count this version adds to."""
        try:
            reason = self._verdict(version)
        except _Skip:
            return "skipped"
        if reason is None:
            return "kept"
        failed = transition(
            version, VersionStatus.FAILED, now=self._clock.now(), failure_reason=reason
        )
        try:
            with self._ports.unit_of_work() as tx:  # status and cover change together
                tx.assets.save_version(failed, expected=VersionStatus.READY)
                tx.assets.drop_cover(failed)
        except InvalidStatusTransitionError:
            return "skipped"  # another run (or writer) changed it first
        return "unreadable" if reason is FailureReason.UNREADABLE_MODEL else "too_large"

    def _verdict(self, version: AssetVersion) -> FailureReason | None:
        """The failure the worker would record today, or None; `_Skip` when it cannot tell."""
        if version.size_bytes > MODEL_MAX_BYTES:
            return FailureReason.MODEL_TOO_LARGE
        storage = self._ports.storage
        stored = storage.head(version.object_key)
        if stored is None or stored.etag != version.etag:
            raise _Skip  # not the file that was made ready; leave it for a person to look at
        with SpooledTemporaryFile(max_size=SPOOL_MAX_BYTES) as buffer:
            if not storage.download(version.object_key, buffer, if_match=stored.etag):
                raise _Skip
            buffer.seek(0)
            try:
                self._render(buffer)
            except UnreadableModelError:
                return FailureReason.UNREADABLE_MODEL
            except ModelTooLargeError:
                return FailureReason.MODEL_TOO_LARGE
            except PreviewCrashedError as error:
                raise _Skip from error
        return None


def _report(counts: Counter[str], *, storage_down: bool = False) -> RecheckReport:
    return RecheckReport(
        checked=counts["checked"],
        kept=counts["kept"],
        unreadable=counts["unreadable"],
        too_large=counts["too_large"],
        skipped=counts["skipped"],
        storage_down=storage_down,
    )


def build_recheck(
    engine: Engine,
    *,
    storage: ObjectStorage,
    clock: Clock | None = None,
    render: Render = render_glb_sandboxed,
    batch_size: int = RECHECK_BATCH_SIZE,
) -> ModelRecheck:
    """Wire the re-check on the API's adapters; the database clock unless a test passes one."""
    ports = RecheckPorts(
        store=SqlMaintenanceStore(engine),
        assets=SqlAssetRepository(engine),
        storage=storage,
        unit_of_work=SqlUnitOfWork(engine),
    )
    return ModelRecheck(ports, clock or DatabaseClock(engine), render=render, batch_size=batch_size)


def main(settings: Settings | None = None) -> int:
    """Run once and log the counts; exit 1 when storage went away (run it again later)."""
    resolved = settings or Settings()
    logging.basicConfig(level=logging.INFO)
    engine = build_engine(resolved)
    started = time.monotonic()
    try:
        report = build_recheck(
            engine, storage=guard_storage(build_storage(resolved), resolved)
        ).run()
    finally:
        engine.dispose()
    logger.info(
        "re-check: %d ready models checked, %d kept, %d unreadable, %d too large, %d skipped"
        " in %.0f ms%s",
        report.checked,
        report.kept,
        report.unreadable,
        report.too_large,
        report.skipped,
        (time.monotonic() - started) * 1000,
        "; storage unavailable, run it again" if report.storage_down else "",
    )
    return 1 if report.storage_down else 0


if __name__ == "__main__":
    raise SystemExit(main())
