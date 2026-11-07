"""Settings read from `KILN_*` environment variables and validated at start-up."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from kiln_api.constants import (
    DB_LOCK_TIMEOUT_MS,
    DB_STATEMENT_TIMEOUT_MS,
    SESSION_COOKIE_LOCAL,
    SESSION_COOKIE_SECURE,
    STORAGE_BREAKER_COOLDOWN_SECONDS,
    STORAGE_BREAKER_FAILURES,
    STORAGE_BULKHEAD_WAIT_SECONDS,
    STORAGE_MAX_CONCURRENT,
    STORAGE_MAX_CONCURRENT_LIMIT,
)
from kiln_api.enums import Environment


class Settings(BaseSettings):
    """Typed configuration; every key is listed in `.env.example`."""

    model_config = SettingsConfigDict(env_prefix="KILN_", env_file=".env", extra="ignore")

    env: Environment = Environment.LOCAL
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://kiln:kiln@127.0.0.1:5432/kiln"
    db_lock_timeout_ms: int = DB_LOCK_TIMEOUT_MS
    db_statement_timeout_ms: int = DB_STATEMENT_TIMEOUT_MS
    # `make web` prints localhost, browsers may also use 127.0.0.1: allow both for local work.
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]
    s3_endpoint: str = "http://127.0.0.1:8333"
    s3_region: str = "us-east-1"
    s3_bucket: str = "kiln-assets"
    s3_access_key: str = "kiln"
    s3_secret_key: SecretStr = SecretStr("kiln-local-secret")
    # Circuit breaker and bulkhead around storage (KILN-23).
    storage_breaker_failures: int = Field(default=STORAGE_BREAKER_FAILURES, gt=0)
    storage_breaker_cooldown_seconds: float = Field(default=STORAGE_BREAKER_COOLDOWN_SECONDS, gt=0)
    storage_max_concurrent: int = Field(
        default=STORAGE_MAX_CONCURRENT, gt=0, le=STORAGE_MAX_CONCURRENT_LIMIT
    )
    storage_bulkhead_wait_seconds: float = Field(default=STORAGE_BULKHEAD_WAIT_SECONDS, gt=0)
    # Session cookie over HTTPS only (`Secure` and the `__Host-` prefix). Unset: on in production,
    # off for local http, where browsers would drop a Secure cookie (KILN-12).
    secure_cookies: bool | None = None

    @field_validator("secure_cookies", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        """`KILN_SECURE_COOKIES=` (as in `.env.example`) means "decide from the environment"."""
        return None if value == "" else value

    @property
    def cookie_secure(self) -> bool:
        """Whether the session cookie is `Secure` (and named with `__Host-`)."""
        if self.secure_cookies is not None:
            return self.secure_cookies
        return self.env is Environment.PRODUCTION

    @property
    def session_cookie_name(self) -> str:
        """`__Host-kiln_session` over HTTPS, `kiln_session` on local http."""
        return SESSION_COOKIE_SECURE if self.cookie_secure else SESSION_COOKIE_LOCAL

    @property
    def trusted_origins(self) -> frozenset[str]:
        """Origins whose cookie-authenticated writes are accepted: the app's own (CSRF check)."""
        return frozenset(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
