"""Composition root: builds adapters from settings and wires the services."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from kiln_api.adapters import S3ObjectStorage
from kiln_api.clock import SystemClock
from kiln_api.config import Settings
from kiln_api.constants import (
    DB_CONNECT_TIMEOUT_SECONDS,
    STORAGE_CONNECT_TIMEOUT_SECONDS,
    STORAGE_PROBE_TIMEOUT_SECONDS,
    STORAGE_READ_TIMEOUT_SECONDS,
    STORAGE_TOTAL_ATTEMPTS,
)
from kiln_api.domain.ids import uuid7
from kiln_api.errors import DatabaseUnavailableError
from kiln_api.ports import Clock, ObjectStorage
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.unit_of_work import SqlUnitOfWork
from kiln_api.resilience import CircuitBreaker, GuardedStorage
from kiln_api.services.assets import AssetService

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@dataclass(frozen=True, slots=True)
class Container:
    """Everything a request may need, built once per process."""

    engine: Engine
    storage: ObjectStorage
    assets: AssetService

    def check_database(self) -> None:
        """Run `SELECT 1`; raise `DatabaseUnavailableError` when it fails."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError from error


def build_engine(settings: Settings) -> Engine:
    """An engine whose sessions cannot wait forever to connect, on a lock or on a query."""
    options = (
        f"-c lock_timeout={settings.db_lock_timeout_ms}"
        f" -c statement_timeout={settings.db_statement_timeout_ms}"
    )
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"options": options, "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )


def _s3_client(settings: Settings, *, connect: float, read: float, attempts: int) -> "S3Client":
    client: S3Client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=connect,
            read_timeout=read,
            retries={"total_max_attempts": attempts, "mode": "standard"},
        ),
    )
    return client


def build_storage(settings: Settings) -> S3ObjectStorage:
    """S3 clients with SigV4 and path-style addressing: one for work, one fast for readiness."""
    work = _s3_client(
        settings,
        connect=STORAGE_CONNECT_TIMEOUT_SECONDS,
        read=STORAGE_READ_TIMEOUT_SECONDS,
        attempts=STORAGE_TOTAL_ATTEMPTS,
    )
    probe = _s3_client(
        settings,
        connect=STORAGE_PROBE_TIMEOUT_SECONDS,
        read=STORAGE_PROBE_TIMEOUT_SECONDS,
        attempts=1,
    )
    return S3ObjectStorage(work, settings.s3_bucket, probe_client=probe)


def guard_storage(storage: ObjectStorage, settings: Settings) -> GuardedStorage:
    """Wrap storage with the circuit breaker and bulkhead configured in `settings` (KILN-23)."""
    breaker = CircuitBreaker(
        failures=settings.storage_breaker_failures,
        cooldown=settings.storage_breaker_cooldown_seconds,
    )
    return GuardedStorage(
        storage,
        breaker,
        max_concurrent=settings.storage_max_concurrent,
        wait_seconds=settings.storage_bulkhead_wait_seconds,
    )


def build_container(
    settings: Settings,
    *,
    engine: Engine | None = None,
    storage: ObjectStorage | None = None,
    clock: Clock | None = None,
) -> Container:
    """Wire real adapters; tests pass their engine and fakes for storage and the clock."""
    engine = engine or build_engine(settings)
    resolved_storage = storage or guard_storage(build_storage(settings), settings)
    service = AssetService(
        SqlAssetRepository(engine),
        resolved_storage,
        clock or SystemClock(),
        uuid7,
        SqlUnitOfWork(engine),
    )
    return Container(engine=engine, storage=resolved_storage, assets=service)
