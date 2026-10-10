from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "production"] = "development"
    db_sslmode: Literal["disable", "prefer", "require", "verify-ca", "verify-full"] = "prefer"
    db_sslrootcert: str | None = None
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: SecretStr
    redirect_cache_enabled: bool = True
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    redirect_cache_ttl_seconds: int = Field(default=30, ge=1, le=300)
    redis_timeout_seconds: float = Field(default=0.2, gt=0, le=5)


    # Required server-side secret; never generate a new key on each startup.
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=7, ge=1, le=30)
    # Local HTTP development only. Enable Secure cookies for HTTPS deployment.
    refresh_cookie_secure: bool = False
    auth_allowed_origins: list[str] = [
        "http://127.0.0.1:8000", "http://localhost:8000",
        "http://127.0.0.1:5173", "http://localhost:5173",
    ]

    @model_validator(mode="after")
    def validate_production(self):
        if self.environment != "production":
            return self
        if not self.refresh_cookie_secure:
            raise ValueError("Production requires Secure refresh cookies")
        if not self.auth_allowed_origins:
            raise ValueError("Production requires explicit frontend origins")
        for origin in self.auth_allowed_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme != "https" or not parsed.hostname or
                    parsed.username or parsed.password or parsed.path or
                    parsed.query or parsed.fragment or "*" in origin or
                    parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
                raise ValueError("Production auth origins must be exact HTTPS origins without paths")
        if self.db_sslmode != "verify-full" or not self.db_sslrootcert:
            raise ValueError("Production requires verify-full database TLS and a root certificate source")
        if self.redirect_cache_enabled and not self.redis_url.get_secret_value().startswith("rediss://"):
            raise ValueError("Production Redis requires a rediss:// TLS URL")
        return self

    def get_database_url(self) -> URL:
        query = {"sslmode": self.db_sslmode}
        if self.db_sslrootcert:
            query["sslrootcert"] = self.db_sslrootcert
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query=query,
        )
