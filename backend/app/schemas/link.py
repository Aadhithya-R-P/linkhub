from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl, StrictBool, field_validator


def reject_url_credentials(value: HttpUrl) -> HttpUrl:
    if value.username is not None or value.password is not None:
        raise ValueError("Destination URL must not contain credentials")
    return value


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_url: HttpUrl

    @field_validator("destination_url")
    @classmethod
    def reject_credentials(cls, value: HttpUrl) -> HttpUrl:
        return reject_url_credentials(value)


class LinkRead(BaseModel):
    id: int
    short_code: str
    destination_url: str
    created_at: datetime
    is_active: bool
    expires_at: datetime | None


class LinkPage(BaseModel):
    items: list[LinkRead]
    next_before_id: int | None


class LinkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination_url: HttpUrl | None = None
    is_active: StrictBool | None = None
    expires_at: AwareDatetime | None = None

    # Defaults allow omission; these validators reject explicitly supplied nulls.
    @field_validator("destination_url")
    @classmethod
    def validate_destination(cls, value: HttpUrl | None) -> HttpUrl:
        if value is None:
            raise ValueError("Destination URL must not be null")
        return reject_url_credentials(value)

    @field_validator("is_active")
    @classmethod
    def validate_active(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Active state must not be null")
        return value
