"""The worker loop: claim a job, process its version, record the outcome atomically."""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from tempfile import SpooledTemporaryFile

from sqlalchemy import Engine

from kiln_api.clock import DatabaseClock
from kiln_api.constants import (
    JOB_MAX_ATTEMPTS,
    MAINTENANCE_INTERVAL_SECONDS,
)
from kiln_api.domain.assets import Asset, AssetVersion, thumbnail_key, transition
from kiln_api.domain.jobs import Job, next_attempt_delay
from kiln_api.enums import AssetKind, FailureReason, VersionStatus
from kiln_api.errors import InvalidStatusTransitionError
from kiln_api.ports import AssetRepository, Clock, JobQueue, ObjectStorage, UnitOfWork
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.idempotency import purge_expired_keys
from kiln_api.repositories.jobs import SqlJobQueue
from kiln_api.repositories.maintenance import SqlMaintenanceStore
from kiln_api.repositories.unit_of_work import SqlUnitOfWork
from kiln_worker.constants import (
    IDLE_POLL_SECONDS,
    MAINTENANCE_CHECK_SECONDS,
    MAX_SOURCE_BYTES_BY_MEDIA_TYPE,
    SPOOL_MAX_BYTES,
)
from kiln_worker.errors import ImageTooLargeError, UnreadableImageError
from kiln_worker.heartbeat import LeaseHeartbeat, LeaseTiming
from kiln_worker.maintenance import Maintenance, MaintenancePorts, MaintenanceReport
from kiln_worker.thumbnail import THUMBNAIL_MEDIA_TYPE, make_thumbnail

logger = logging.getLogger("kiln_worker")

_TIMING = LeaseTiming()


@dataclass(frozen=True, slots=True)
class WorkerPorts:
    """Everything the worker talks to."""

    jobs: JobQueue
    assets: AssetRepository
    storage: ObjectStorage
    unit_of_work: UnitOfWork


class Worker:
    """Processes one job at a time; safe to run several copies (SKIP LOCKED + leases)."""

    def __init__(
        self,
        ports: WorkerPorts,
        clock: Clock,
        *,
        database_clock: bool = True,
        maintenance: Maintenance | None = None,
        timing: LeaseTiming = _TIMING,
    ) -> None:
        """Receive every collaborator through its port.

        With `database_clock`, leases and retries use the database's `now()` so workers with
        skewed clocks agree; tests turn it off and drive time through `clock`.
        """
        self._jobs = ports.jobs
        self._assets = ports.assets
        self._storage = ports.storage
        self._unit_of_work = ports.unit_of_work
        self._clock = clock
        self._database_clock = database_clock
        self._maintenance = maintenance
        self._next_maintenance_check = 0.0
        self._timing = timing
        self._heartbeat: LeaseHeartbeat | None = None

    def run(self, *, stop: threading.Event, idle_seconds: float = IDLE_POLL_SECONDS) -> None:
        """Work until `stop` is set; never dies on an error, sleeps when idle or failing."""
        while not stop.is_set():
            self.maintain_if_due()
            try:
                worked = self.run_once()
            except Exception as error:
                logger.exception("worker iteration failed: %s", type(error).__name__)
                worked = False
            if not worked:
                stop.wait(idle_seconds)

    def maintain_if_due(self, *, now: float | None = None) -> MaintenanceReport | None:
        """Ask at most once a minute whether maintenance is due; its failures never stop jobs."""
        current = time.monotonic() if now is None else now
        if self._maintenance is None or current < self._next_maintenance_check:
            return None
        self._next_maintenance_check = current + MAINTENANCE_CHECK_SECONDS
        try:
            return self._maintenance.run_if_due()
        except Exception as error:
            cause = getattr(error, "cause_code", "") or type(error).__name__
            logger.exception("maintenance failed: %s", cause)
            return None

    def run_once(self) -> bool:
        """Bury exhausted jobs, then claim and process one job; False when nothing ran."""
        self._bury_exhausted()
        job = self._jobs.claim(
            lease=self._timing.lease, max_attempts=JOB_MAX_ATTEMPTS, now=self._queue_now()
        )
        if job is None:
            return False
        logger.info(
            "job %s for version %s: started (attempt %d)", job.id, job.version_id, job.attempts
        )
        started = time.monotonic()
        heartbeat = LeaseHeartbeat(self._jobs, job, timing=self._timing, queue_now=self._queue_now)
        self._heartbeat = heartbeat
        try:
            with heartbeat:  # long jobs keep their lease while they run (KILN-24)
                outcome = self._handle(job)
        finally:
            self._heartbeat = None
        logger.info(
            "job %s for version %s: %s in %.0f ms (attempt %d)",
            job.id,
            job.version_id,
            outcome,
            (time.monotonic() - started) * 1000,
            job.attempts,
        )
        return True

    def _queue_now(self) -> datetime | None:
        return None if self._database_clock else self._clock.now()

    def _handle(self, job: Job) -> str:
        try:
            version = self._assets.get_version(job.version_id)
            if version.status is not VersionStatus.PROCESSING:
                return self._close(job, f"skipped ({version.status})")
            reason = self._render(self._assets.get(version.asset_id), version)
            return self._finish(job, version, reason)
        except Exception as error:
            return self._retry_or_give_up(job, error)

    def _render(self, asset: Asset, version: AssetVersion) -> FailureReason | None:
        stored = self._storage.head(version.object_key)
        if stored is None or (version.etag is not None and stored.etag != version.etag):
            return FailureReason.UPLOAD_CHANGED
        if asset.kind is AssetKind.MODEL:
            return None  # 3D previews arrive with KILN-5
        if version.size_bytes > MAX_SOURCE_BYTES_BY_MEDIA_TYPE.get(
            version.content_type, version.size_bytes
        ):
            return FailureReason.IMAGE_TOO_LARGE
        return self._render_image(version, stored.etag)

    def _render_image(self, version: AssetVersion, etag: str) -> FailureReason | None:
        with SpooledTemporaryFile(max_size=SPOOL_MAX_BYTES) as buffer:
            if not self._storage.download(version.object_key, buffer, if_match=etag):
                return FailureReason.UPLOAD_CHANGED  # replaced between HEAD and GET
            buffer.seek(0)
            try:
                preview = make_thumbnail(buffer, version.content_type)
            except UnreadableImageError:
                return FailureReason.UNREADABLE_IMAGE
            except ImageTooLargeError:
                return FailureReason.IMAGE_TOO_LARGE
        self._storage.upload(thumbnail_key(version), preview, THUMBNAIL_MEDIA_TYPE)
        return None

    def _stop_heartbeat(self) -> None:
        """No extension may race the outcome write (KILN-24)."""
        if self._heartbeat is not None:
            self._heartbeat.stop()

    def _finish(self, job: Job, version: AssetVersion, reason: FailureReason | None) -> str:
        self._stop_heartbeat()
        now = self._clock.now()
        status = VersionStatus.READY if reason is None else VersionStatus.FAILED
        done = transition(version, status, now=now, failure_reason=reason)
        try:
            with self._unit_of_work() as tx:  # version, cover and job change together
                _require_owner(tx.jobs.finish(job, now=self._queue_now()))
                tx.assets.save_version(done, expected=VersionStatus.PROCESSING)
                if reason is None:
                    tx.assets.promote_cover(done)
        except _LeaseLostError:
            return "lease lost; another worker owns the job"
        except InvalidStatusTransitionError:
            return self._close(job, "skipped (changed meanwhile)")
        return status.value if reason is None else f"failed {reason.value}"

    def _close(self, job: Job, outcome: str) -> str:
        self._stop_heartbeat()
        if not self._jobs.finish(job, now=self._queue_now()):
            return "lease lost; another worker owns the job"
        return outcome

    def _retry_or_give_up(self, job: Job, error: Exception) -> str:
        self._stop_heartbeat()
        cause = getattr(error, "cause_code", "") or type(error).__name__
        delay = next_attempt_delay(job)
        if delay is not None:
            if not self._jobs.retry(job, delay=delay, error=cause, now=self._queue_now()):
                return "lease lost; another worker owns the job"
            return f"retry in {delay.total_seconds():.0f} s ({cause})"
        self._give_up(job, cause)
        return f"gave up ({cause})"

    def _give_up(self, job: Job, cause: str) -> None:
        with self._unit_of_work() as tx:
            if not tx.jobs.bury(job, error=cause, now=self._queue_now()):
                return
            version = tx.assets.get_version(job.version_id)
            if version.status is not VersionStatus.PROCESSING:
                return
            gave_up = transition(
                version,
                VersionStatus.FAILED,
                now=self._clock.now(),
                failure_reason=FailureReason.PROCESSING_GAVE_UP,
            )
            try:
                tx.assets.save_version(gave_up, expected=VersionStatus.PROCESSING)
            except InvalidStatusTransitionError:
                return

    def _bury_exhausted(self) -> None:
        """Jobs that crashed the worker on every attempt are buried and their versions failed."""
        exhausted = self._jobs.exhausted_jobs(max_attempts=JOB_MAX_ATTEMPTS, now=self._queue_now())
        for job in exhausted:
            logger.warning("job %s exhausted its attempts while leased; burying", job.id)
            self._give_up(job, "crashed on every attempt")


class _LeaseLostError(Exception):
    """This worker's claim expired and another worker re-claimed the job."""


def _require_owner(owned: bool) -> None:
    if not owned:
        msg = "lease lost"
        raise _LeaseLostError(msg)


def build_worker(
    engine: Engine,
    *,
    storage: ObjectStorage,
    clock: Clock | None = None,
    maintenance_interval: timedelta = timedelta(seconds=MAINTENANCE_INTERVAL_SECONDS),
    timing: LeaseTiming = _TIMING,
) -> Worker:
    """Wire the worker on the API's adapters; an injected clock also drives the queue (tests)."""
    assets = SqlAssetRepository(engine)
    ports = WorkerPorts(
        jobs=SqlJobQueue(engine),
        assets=assets,
        storage=storage,
        unit_of_work=SqlUnitOfWork(engine),
    )
    database_clock = clock is None
    resolved = clock or DatabaseClock(engine)
    maintenance = Maintenance(
        MaintenancePorts(
            store=SqlMaintenanceStore(engine),
            assets=assets,
            storage=storage,
            purge_keys=lambda limit: purge_expired_keys(
                engine, now=None if database_clock else resolved.now(), limit=limit
            ),
        ),
        resolved,
        interval=maintenance_interval,
        database_clock=database_clock,
    )
    return Worker(
        ports, resolved, database_clock=database_clock, maintenance=maintenance, timing=timing
    )
