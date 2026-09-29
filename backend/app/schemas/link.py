from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_url: HttpUrl

    @field_validator("destination_url")
    @classmethod
    def reject_credentials(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("Destination URL must not contain credentials")
        return value


class LinkRead(BaseModel):
    id: int
    short_code: str
    destination_url: str
    created_at: datetime
    is_active: bool
    expires_at: datetime | None
