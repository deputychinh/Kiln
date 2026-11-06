"""Scheduled maintenance (KILN-22): expire abandoned uploads, sweep staging, purge old keys."""

import logging
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import batched, chain, islice
from uuid import UUID

from kiln_api.constants import (
    MAINTENANCE_BATCH_SIZE,
    MAINTENANCE_LOOKUP_CHUNK,
    MAINTENANCE_PURGE_BATCHES,
    MAINTENANCE_SCAN_LIMIT,
    MAINTENANCE_TASK,
    UPLOAD_ABANDONED_AFTER_HOURS,
    UPLOAD_KEY_PREFIX,
)
from kiln_api.domain.assets import AssetVersion, transition, upload_key
from kiln_api.enums import FailureReason, VersionStatus
from kiln_api.errors import InvalidStatusTransitionError, StorageUnavailableError
from kiln_api.ports import AssetRepository, Clock, MaintenanceStore, ObjectStorage

logger = logging.getLogger("kiln_worker")

_ABANDONED_AFTER = timedelta(hours=UPLOAD_ABANDONED_AFTER_HOURS)
_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# Only keys the API's signed forms can write: uploads/<asset id>/<version id>.
_STAGING_KEY = re.compile(rf"^{UPLOAD_KEY_PREFIX}/{_UUID}/(?P<version>{_UUID})$")


@dataclass(frozen=True, slots=True)
class MaintenanceReport:
    """What one run cleaned up; `storage_down` means a sweep stopped early and resumes next run."""

    expired_versions: int
    deleted_objects: int
    purged_keys: int
    storage_down: bool = False


@dataclass(frozen=True, slots=True)
class MaintenancePorts:
    """Everything maintenance talks to."""

    store: MaintenanceStore
    assets: AssetRepository
    storage: ObjectStorage
    purge_keys: Callable[[int], int]


class _Tally:
    """Counts of one run; a storage outage stops the storage work but not the key purge."""

    def __init__(self) -> None:
        self.expired = 0
        self.deleted = 0
        self.storage_down = False


class Maintenance:
    """Runs at most once per `interval` across every worker; each sweep handles one batch.

    The lease records when a run started, not when it ended: with an interval shorter than a run,
    two runs may overlap, which is safe because every step is idempotent.
    """

    def __init__(
        self,
        ports: MaintenancePorts,
        clock: Clock,
        *,
        interval: timedelta,
        database_clock: bool = True,
    ) -> None:
        """Receive the collaborators; `database_clock` as in `Worker`."""
        self._store = ports.store
        self._assets = ports.assets
        self._storage = ports.storage
        self._purge_keys = ports.purge_keys
        self._clock = clock
        self._interval = interval
        self._database_clock = database_clock

    def run_if_due(self) -> MaintenanceReport | None:
        """Run when no worker started a run within the interval; None when not due."""
        if not self._store.try_start(MAINTENANCE_TASK, every=self._interval, now=self._lease_now()):
            return None
        started = time.monotonic()
        tally = _Tally()
        try:
            self._expire_abandoned_uploads(tally)
            self._sweep_staging(tally)
        except StorageUnavailableError as error:
            tally.storage_down = True
            logger.warning(
                "maintenance: storage unavailable (%s); the rest waits for the next run",
                error.cause_code or type(error).__name__,
            )
        report = MaintenanceReport(
            expired_versions=tally.expired,
            deleted_objects=tally.deleted,
            purged_keys=self._purge_expired_keys(),
            storage_down=tally.storage_down,
        )
        logger.info(
            "maintenance: %d abandoned versions expired, %d staging objects deleted,"
            " %d idempotency keys purged in %.0f ms",
            report.expired_versions,
            report.deleted_objects,
            report.purged_keys,
            (time.monotonic() - started) * 1000,
        )
        return report

    def _purge_expired_keys(self) -> int:
        """Purge batch after batch while full batches come back, up to a bounded number."""
        purged = 0
        for _ in range(MAINTENANCE_PURGE_BATCHES):
            removed = self._purge_keys(MAINTENANCE_BATCH_SIZE)
            purged += removed
            if removed < MAINTENANCE_BATCH_SIZE:
                break
        return purged

    def _lease_now(self) -> datetime | None:
        return None if self._database_clock else self._clock.now()

    def _expire_abandoned_uploads(self, tally: _Tally) -> None:
        """Fail versions never completed, then drop their objects (the save always comes first)."""
        stale = self._store.stale_pending_versions(
            older_than=_ABANDONED_AFTER, limit=MAINTENANCE_BATCH_SIZE, now=self._lease_now()
        )
        for chunk in batched(stale, MAINTENANCE_LOOKUP_CHUNK):
            for version in self._assets.versions_by_id(chunk).values():
                if self._expire(version):
                    tally.expired += 1

    def _expire(self, version: AssetVersion) -> bool:
        try:
            failed = transition(
                version,
                VersionStatus.FAILED,
                now=self._clock.now(),
                failure_reason=FailureReason.UPLOAD_EXPIRED,
            )
            self._assets.save_version(failed, expected=VersionStatus.PENDING_UPLOAD)
        except InvalidStatusTransitionError:
            return False  # completed meanwhile (before or after the read): the completion won
        # A completion racing with this expiry may already have promoted the file to its final
        # key; the version is failed for good, so that copy is garbage too.
        self._storage.delete(upload_key(version))
        self._storage.delete(version.object_key)
        return True

    def _sweep_staging(self, tally: _Tally) -> None:
        """Delete old staging objects whose version is gone or no longer waiting for them.

        Only deletions count toward the batch; keys that must stay are skipped without counting,
        and the listing is cut after `MAINTENANCE_SCAN_LIMIT` keys so the run stays bounded.
        """
        pages = self._storage.iter_key_pages(
            f"{UPLOAD_KEY_PREFIX}/", older_than=self._clock.now() - _ABANDONED_AFTER
        )
        keys = islice(chain.from_iterable(pages), MAINTENANCE_SCAN_LIMIT)
        for chunk in batched(_kiln_staging_keys(keys), MAINTENANCE_LOOKUP_CHUNK):
            waiting = self._waiting_versions([version_id for _, version_id in chunk])
            for key, version_id in chunk:
                if version_id in waiting:
                    continue  # the expiry above handles it once the version is abandoned
                self._storage.delete(key)
                tally.deleted += 1
                if tally.deleted >= MAINTENANCE_BATCH_SIZE:
                    return

    def _waiting_versions(self, version_ids: list[UUID]) -> set[UUID]:
        versions = self._assets.versions_by_id(version_ids)
        return {
            version_id
            for version_id, version in versions.items()
            if version.status is VersionStatus.PENDING_UPLOAD
        }


def _kiln_staging_keys(keys: Iterable[str]) -> Iterable[tuple[str, UUID]]:
    """Keys written by a Kiln form, with their version id; never touch what we do not understand."""
    for key in keys:
        match = _STAGING_KEY.match(key)
        if match is not None:
            yield key, UUID(match["version"])
