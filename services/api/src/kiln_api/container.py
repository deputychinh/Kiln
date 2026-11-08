"""Composition root: builds adapters from settings and wires the services."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from kiln_api.adapters import Argon2PasswordHasher, S3ObjectStorage
from kiln_api.clock import SystemClock
from kiln_api.config import Settings
from kiln_api.constants import (
    ARGON2_MEMORY_KIB,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    DB_CONNECT_TIMEOUT_SECONDS,
    DB_KEEPALIVES_COUNT,
    DB_KEEPALIVES_IDLE_SECONDS,
    DB_KEEPALIVES_INTERVAL_SECONDS,
    DB_TCP_USER_TIMEOUT_MS,
    STORAGE_CONNECT_TIMEOUT_SECONDS,
    STORAGE_PROBE_TIMEOUT_SECONDS,
    STORAGE_READ_TIMEOUT_SECONDS,
    STORAGE_TOTAL_ATTEMPTS,
)
from kiln_api.domain.ids import uuid7
from kiln_api.errors import DatabaseUnavailableError
from kiln_api.ports import Clock, ObjectStorage, PasswordHasher
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.repositories.identity import SqlIdentityStore
from kiln_api.repositories.unit_of_work import SqlUnitOfWork
from kiln_api.resilience import CircuitBreaker, GuardedStorage
from kiln_api.services.assets import AssetService
from kiln_api.services.comments import CommentService
from kiln_api.services.identity import IdentityService
from kiln_api.services.reviews import ReviewService
from kiln_api.signing import SigningCredentials

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@dataclass(frozen=True, slots=True)
class Container:
    """Everything a request may need, built once per process."""

    engine: Engine
    storage: ObjectStorage
    assets: AssetService
    identity: IdentityService
    comments: CommentService
    reviews: ReviewService

    def check_database(self) -> None:
        """Run `SELECT 1`; raise `DatabaseUnavailableError` when it fails."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError from error


def build_engine(settings: Settings) -> Engine:
    """An engine whose sessions never wait forever to connect, on a lock, a query or a dead link."""
    options = (
        f"-c lock_timeout={settings.db_lock_timeout_ms}"
        f" -c statement_timeout={settings.db_statement_timeout_ms}"
    )
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={
            "options": options,
            "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
            "keepalives": 1,
            "keepalives_idle": DB_KEEPALIVES_IDLE_SECONDS,
            "keepalives_interval": DB_KEEPALIVES_INTERVAL_SECONDS,
            "keepalives_count": DB_KEEPALIVES_COUNT,
            "tcp_user_timeout": DB_TCP_USER_TIMEOUT_MS,
        },
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
    signing = SigningCredentials(
        endpoint=settings.s3_endpoint,
        region=settings.s3_region,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key.get_secret_value(),
    )
    return S3ObjectStorage(work, settings.s3_bucket, signing=signing, probe_client=probe)


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
    hasher: PasswordHasher | None = None,
) -> Container:
    """Wire real adapters; tests pass their engine and fakes for storage and the clock."""
    engine = engine or build_engine(settings)
    resolved_storage = storage or guard_storage(build_storage(settings), settings)
    resolved_clock = clock or SystemClock()
    service = AssetService(
        SqlAssetRepository(engine),
        resolved_storage,
        resolved_clock,
        uuid7,
        SqlUnitOfWork(engine),
    )
    identity = IdentityService(
        SqlIdentityStore(engine), hasher or build_hasher(), resolved_clock, uuid7
    )
    comments = CommentService(resolved_clock, uuid7, SqlUnitOfWork(engine))
    return Container(
        engine=engine,
        storage=resolved_storage,
        assets=service,
        identity=identity,
        comments=comments,
        reviews=ReviewService(resolved_clock, uuid7, SqlUnitOfWork(engine)),
    )


def build_hasher() -> Argon2PasswordHasher:
    """Argon2id with the OWASP parameters in `constants`."""
    return Argon2PasswordHasher(
        memory_kib=ARGON2_MEMORY_KIB, time_cost=ARGON2_TIME_COST, parallelism=ARGON2_PARALLELISM
    )
