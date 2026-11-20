"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Pulse API and workers."""

    model_config = SettingsConfigDict(
        env_prefix="PULSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="development", description="Runtime environment name")
    debug: bool = False
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "pulse"
    postgres_password: SecretStr = SecretStr("pulse")
    postgres_db: str = "pulse"

    redis_url: str = "redis://localhost:6379/0"

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: SecretStr = SecretStr("")
    clickhouse_db: str = "pulse"
    clickhouse_enabled: bool = True

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: SecretStr = SecretStr("minio")
    s3_secret_key: SecretStr = SecretStr("minio123")
    s3_bucket: str = "pulse"
    s3_region: str = "us-east-1"

    jwt_secret: SecretStr = SecretStr("change-me-in-production-use-a-long-random-string")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Fernet key (url-safe base64 32-byte). If unset, derived from jwt_secret (dev only).
    credentials_encryption_key: SecretStr | None = None

    # CORS — empty means no browser origins (secure default). Comma-separated list.
    cors_allow_origins: str = Field(
        default="",
        description="Comma-separated origins; empty disables CORS reflection",
    )
    cors_allow_credentials: bool = False

    # API rate limiting
    api_rate_limit_enabled: bool = True
    api_rate_limit_requests: int = Field(default=120, ge=1)
    api_rate_limit_window_seconds: float = Field(default=60.0, gt=0)

    # SSRF: resolve DNS when validating outbound URLs (disable only in special tests)
    ssrf_resolve_dns: bool = True

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _strip_origins(cls, value: object) -> object:
        if value is None:
            return ""
        return value

    def cors_origins_list(self) -> list[str]:
        if not self.cors_allow_origins.strip():
            return []
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL for PostgreSQL (asyncpg)."""
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync SQLAlchemy URL for Alembic migrations (psycopg)."""
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
