"""Scheduled maintenance (KILN-22): expire abandoned uploads, sweep staging, purge old keys."""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from kiln_api.constants import (
    MAINTENANCE_BATCH_SIZE,
    MAINTENANCE_TASK,
    UPLOAD_ABANDONED_AFTER_HOURS,
    UPLOAD_KEY_PREFIX,
)
from kiln_api.domain.assets import transition, upload_key
from kiln_api.enums import FailureReason, VersionStatus
from kiln_api.errors import AssetVersionNotFoundError, InvalidStatusTransitionError
from kiln_api.ports import AssetRepository, Clock, ObjectStorage
from kiln_api.repositories.maintenance import SqlMaintenanceStore

logger = logging.getLogger("kiln_worker")

_ABANDONED_AFTER = timedelta(hours=UPLOAD_ABANDONED_AFTER_HOURS)
_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# Only keys the API's signed forms can write: uploads/<asset id>/<version id>.
_STAGING_KEY = re.compile(rf"^{UPLOAD_KEY_PREFIX}/{_UUID}/(?P<version>{_UUID})$")


@dataclass(frozen=True, slots=True)
class MaintenanceReport:
    """What one run cleaned up."""

    expired_versions: int
    deleted_objects: int
    purged_keys: int


@dataclass(frozen=True, slots=True)
class MaintenancePorts:
    """Everything maintenance talks to."""

    store: SqlMaintenanceStore
    assets: AssetRepository
    storage: ObjectStorage
    purge_keys: Callable[[int], int]


class Maintenance:
    """Runs at most once per `interval` across every worker; each sweep handles one batch."""

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
        report = MaintenanceReport(
            expired_versions=self._expire_abandoned_uploads(),
            deleted_objects=self._sweep_staging(),
            purged_keys=self._purge_keys(MAINTENANCE_BATCH_SIZE),
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

    def _lease_now(self) -> datetime | None:
        return None if self._database_clock else self._clock.now()

    def _expire_abandoned_uploads(self) -> int:
        """Fail versions never completed, then drop their staging object (the save comes first)."""
        expired = 0
        stale = self._store.stale_pending_versions(
            older_than=_ABANDONED_AFTER, limit=MAINTENANCE_BATCH_SIZE, now=self._lease_now()
        )
        for version_id in stale:
            version = self._assets.get_version(version_id)
            try:
                failed = transition(
                    version,
                    VersionStatus.FAILED,
                    now=self._clock.now(),
                    failure_reason=FailureReason.UPLOAD_EXPIRED,
                )
                self._assets.save_version(failed, expected=VersionStatus.PENDING_UPLOAD)
            except InvalidStatusTransitionError:
                continue  # completed meanwhile (before or after the read): the completion won
            self._storage.delete(upload_key(version))
            expired += 1
        return expired

    def _sweep_staging(self) -> int:
        """Delete old staging objects whose version is gone or no longer waiting for them."""
        deleted = 0
        keys = self._storage.list_keys(
            f"{UPLOAD_KEY_PREFIX}/",
            older_than=self._clock.now() - _ABANDONED_AFTER,
            limit=MAINTENANCE_BATCH_SIZE,
        )
        for key in keys:
            match = _STAGING_KEY.match(key)
            if match is None:
                continue  # not written by a Kiln form: never delete what we do not understand
            if self._is_waiting(UUID(match["version"])):
                continue  # the expiry above handles it once the version is abandoned
            self._storage.delete(key)
            deleted += 1
        return deleted

    def _is_waiting(self, version_id: UUID) -> bool:
        try:
            version = self._assets.get_version(version_id)
        except AssetVersionNotFoundError:
            return False
        return version.status is VersionStatus.PENDING_UPLOAD
