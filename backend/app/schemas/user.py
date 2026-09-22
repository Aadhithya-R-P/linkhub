from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=15, max_length=128)
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        # LinkHub deliberately treats the whole address as case-insensitive.
        return value.lower()


class UserRead(BaseModel):
    #normally Pydantic reads from dictionary, this allows it to read from Objects
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str | None
    created_at: datetime
