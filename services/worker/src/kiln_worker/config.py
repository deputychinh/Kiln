"""Worker settings read from `KILN_*` environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from kiln_api.constants import MAINTENANCE_INTERVAL_SECONDS
from kiln_worker.constants import (
    JOB_STOP_GRACE_MAX_SECONDS,
    JOB_STOP_GRACE_SECONDS,
    WORKER_MAX_JOBS,
    WORKER_MAX_RSS_MB,
)


class WorkerSettings(BaseSettings):
    """Typed configuration; every key is listed in `.env.example`."""

    model_config = SettingsConfigDict(env_prefix="KILN_", env_file=".env", extra="ignore")

    log_level: str = "INFO"
    poll_interval_seconds: float = 1.0
    # One maintenance run per interval across every worker (KILN-22).
    maintenance_interval_seconds: int = Field(default=MAINTENANCE_INTERVAL_SECONDS, gt=0)
    # A fresh worker process after this many jobs or this much peak memory (KILN-25).
    worker_max_jobs: int = Field(default=WORKER_MAX_JOBS, gt=0)
    worker_max_rss_mb: int = Field(default=WORKER_MAX_RSS_MB, gt=0)
    # A running job gets this long to finish after a stop is asked (KILN-28).
    job_stop_grace_seconds: float = Field(
        default=JOB_STOP_GRACE_SECONDS, gt=0, le=JOB_STOP_GRACE_MAX_SECONDS
    )
