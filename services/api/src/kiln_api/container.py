"""Composition root: builds adapters from settings and wires the services."""

from dataclasses import dataclass

import boto3
from botocore.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from kiln_api.adapters import S3ObjectStorage
from kiln_api.clock import SystemClock
from kiln_api.config import Settings
from kiln_api.constants import (
    DB_LOCK_TIMEOUT_MS,
    DB_STATEMENT_TIMEOUT_MS,
    STORAGE_MAX_ATTEMPTS,
    STORAGE_TIMEOUT_SECONDS,
)
from kiln_api.domain.ids import uuid7
from kiln_api.errors import DatabaseUnavailableError
from kiln_api.ports import Clock, ObjectStorage
from kiln_api.repositories.assets import SqlAssetRepository
from kiln_api.services.assets import AssetService


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


def build_engine(database_url: str) -> Engine:
    """An engine whose sessions cannot wait forever on a lock or a query."""
    options = f"-c lock_timeout={DB_LOCK_TIMEOUT_MS} -c statement_timeout={DB_STATEMENT_TIMEOUT_MS}"
    return create_engine(database_url, pool_pre_ping=True, connect_args={"options": options})


def build_storage(settings: Settings) -> S3ObjectStorage:
    """An S3 client with SigV4, path-style addressing, timeouts and bounded retries."""
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=STORAGE_TIMEOUT_SECONDS,
            read_timeout=STORAGE_TIMEOUT_SECONDS,
            retries={"max_attempts": STORAGE_MAX_ATTEMPTS, "mode": "standard"},
        ),
    )
    return S3ObjectStorage(client, settings.s3_bucket)


def build_container(
    settings: Settings,
    *,
    engine: Engine | None = None,
    storage: ObjectStorage | None = None,
    clock: Clock | None = None,
) -> Container:
    """Wire real adapters; tests pass their engine and fakes for storage and the clock."""
    engine = engine or build_engine(settings.database_url)
    resolved_storage = storage or build_storage(settings)
    service = AssetService(
        SqlAssetRepository(engine), resolved_storage, clock or SystemClock(), uuid7
    )
    return Container(engine=engine, storage=resolved_storage, assets=service)
