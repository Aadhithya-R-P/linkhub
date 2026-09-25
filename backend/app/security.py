from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import secrets

import jwt
from pwdlib import PasswordHash

from app.config import Settings

password_hasher = PasswordHash.recommended()


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    # Random 256-bit tokens do not need the slow password hashing used for passwords.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


@lru_cache(maxsize=1)
def get_dummy_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "iss": "linkhub",
            "aud": "linkhub-api",
            "token_type": "access",
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> int:
    claims = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer="linkhub",
        audience="linkhub-api",
        options={"require": ["sub", "iat", "exp", "iss", "aud", "token_type"]},
    )
    subject = claims["sub"]
    if (
        claims["token_type"] != "access"
        or not isinstance(subject, str)
        or not subject.isascii()
        or not subject.isdecimal()
        or len(subject) > 10
        or not 1 <= int(subject) <= 2147483647
        or str(int(subject)) != subject
    ):
        raise jwt.InvalidTokenError("Invalid access token claims")
    return int(subject)
