from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
    )

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: SecretStr


    # Required server-side secret; never generate a new key on each startup.
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=15, ge=1, le=60)

    def get_database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
