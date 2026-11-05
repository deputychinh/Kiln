"""The worker loop: claim a job, process its version, record the outcome atomically."""

import logging
import threading
import time
from datetime import timedelta
from tempfile import SpooledTemporaryFile

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from kiln_api.clock import SystemClock
from kiln_api.constants import JOB_LEASE_SECONDS
from kiln_api.domain.assets import Asset, AssetVersion, thumbnail_key, transition
from kiln_api.domain.jobs import Job, next_attempt_at
from kiln_api.enums import AssetKind, FailureReason, VersionStatus
from kiln_api.errors import DomainError, InvalidStatusTransitionError
from kiln_api.ports import AssetRepository, Clock, JobQueue, ObjectStorage, UnitOfWork
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.jobs import SqlJobQueue
from kiln_api.repositories.unit_of_work import SqlUnitOfWork
from kiln_worker.constants import IDLE_POLL_SECONDS, SPOOL_MAX_BYTES
from kiln_worker.errors import ImageTooLargeError, UnreadableImageError
from kiln_worker.thumbnail import THUMBNAIL_MEDIA_TYPE, make_thumbnail

logger = logging.getLogger("kiln_worker")

_LEASE_SECONDS = float(JOB_LEASE_SECONDS)


class Worker:
    """Processes one job at a time; safe to run several copies (SKIP LOCKED + leases)."""

    def __init__(
        self,
        *,
        jobs: JobQueue,
        assets: AssetRepository,
        storage: ObjectStorage,
        unit_of_work: UnitOfWork,
        clock: Clock,
    ) -> None:
        """Receive every collaborator through its port."""
        self._jobs = jobs
        self._assets = assets
        self._storage = storage
        self._unit_of_work = unit_of_work
        self._clock = clock

    def run(self, *, stop: threading.Event, idle_seconds: float = IDLE_POLL_SECONDS) -> None:
        """Work until `stop` is set; sleep between polls only when the queue is empty."""
        while not stop.is_set():
            if not self.run_once():
                stop.wait(idle_seconds)

    def run_once(self) -> bool:
        """Claim and process one job; False when nothing was runnable."""
        job = self._jobs.claim(now=self._clock.now(), lease=timedelta(seconds=_LEASE_SECONDS))
        if job is None:
            return False
        started = time.monotonic()
        outcome = self._handle(job)
        logger.info(
            "job %s for version %s: %s in %.0f ms (attempt %d)",
            job.id,
            job.version_id,
            outcome,
            (time.monotonic() - started) * 1000,
            job.attempts,
        )
        return True

    def _handle(self, job: Job) -> str:
        version = self._assets.get_version(job.version_id)
        if version.status is not VersionStatus.PROCESSING:
            self._jobs.finish(job.id, now=self._clock.now())
            return f"skipped ({version.status})"
        try:
            reason = self._render(self._assets.get(version.asset_id), version)
        except (DomainError, SQLAlchemyError) as error:
            return self._retry_or_give_up(job, version, error)
        return self._finish(job, version, reason)

    def _render(self, asset: Asset, version: AssetVersion) -> FailureReason | None:
        stored = self._storage.head(version.object_key)
        if stored is None or stored.etag != version.etag:
            return FailureReason.UPLOAD_CHANGED
        if asset.kind is AssetKind.MODEL:
            return None  # 3D previews arrive with KILN-5
        with SpooledTemporaryFile(max_size=SPOOL_MAX_BYTES) as buffer:
            self._storage.download(version.object_key, buffer)
            buffer.seek(0)
            try:
                preview = make_thumbnail(buffer, version.content_type)
            except UnreadableImageError:
                return FailureReason.UNREADABLE_IMAGE
            except ImageTooLargeError:
                return FailureReason.IMAGE_TOO_LARGE
        self._storage.upload(thumbnail_key(version), preview, THUMBNAIL_MEDIA_TYPE)
        return None

    def _finish(self, job: Job, version: AssetVersion, reason: FailureReason | None) -> str:
        now = self._clock.now()
        status = VersionStatus.READY if reason is None else VersionStatus.FAILED
        done = transition(version, status, now=now, failure_reason=reason)
        try:
            with self._unit_of_work() as tx:  # version, cover and job change together
                tx.assets.save_version(done, expected=VersionStatus.PROCESSING)
                if reason is None:
                    tx.assets.promote_cover(done)
                tx.jobs.finish(job.id, now=now)
        except InvalidStatusTransitionError:
            self._jobs.finish(job.id, now=now)
            return "skipped (changed meanwhile)"
        return status.value if reason is None else f"failed {reason.value}"

    def _retry_or_give_up(self, job: Job, version: AssetVersion, error: Exception) -> str:
        now = self._clock.now()
        cause = getattr(error, "cause_code", "") or type(error).__name__
        retry_at = next_attempt_at(job, now=now)
        if retry_at is not None:
            self._jobs.retry(job.id, run_after=retry_at, error=cause, now=now)
            return f"retry at {retry_at.isoformat()} ({cause})"
        gave_up = transition(
            version, VersionStatus.FAILED, now=now, failure_reason=FailureReason.PROCESSING_GAVE_UP
        )
        with self._unit_of_work() as tx:
            tx.assets.save_version(gave_up, expected=VersionStatus.PROCESSING)
            tx.jobs.bury(job.id, error=cause, now=now)
        return f"gave up ({cause})"


def build_worker(engine: Engine, *, storage: ObjectStorage, clock: Clock | None = None) -> Worker:
    """Wire the worker on the API's adapters (one schema, one set of rules)."""
    return Worker(
        jobs=SqlJobQueue(engine),
        assets=SqlAssetRepository(engine),
        storage=storage,
        unit_of_work=SqlUnitOfWork(engine),
        clock=clock or SystemClock(),
    )
