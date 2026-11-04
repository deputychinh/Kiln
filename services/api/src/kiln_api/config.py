"""Settings read from `KILN_*` environment variables and validated at start-up."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from kiln_api.enums import Environment


class Settings(BaseSettings):
    """Typed configuration; every key is listed in `.env.example`."""

    model_config = SettingsConfigDict(env_prefix="KILN_", env_file=".env", extra="ignore")

    env: Environment = Environment.LOCAL
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://kiln:kiln@127.0.0.1:5432/kiln"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://127.0.0.1:4173"]
    s3_endpoint: str = "http://127.0.0.1:8333"
    s3_region: str = "us-east-1"
    s3_bucket: str = "kiln-assets"
    s3_access_key: str = "kiln"
    s3_secret_key: SecretStr = SecretStr("kiln-local-secret")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
