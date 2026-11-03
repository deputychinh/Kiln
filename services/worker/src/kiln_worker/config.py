"""Worker settings read from `KILN_*` environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Typed configuration; every key is listed in `.env.example`."""

    model_config = SettingsConfigDict(env_prefix="KILN_", env_file=".env", extra="ignore")

    log_level: str = "INFO"
    poll_interval_seconds: float = 1.0
