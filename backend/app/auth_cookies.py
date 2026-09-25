from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response

from app.config import Settings

REFRESH_COOKIE_NAME = "linkhub_refresh"
REFRESH_COOKIE_PATH = "/api/auth"


def require_trusted_auth_origin(request: Request) -> None:
    """Protect cookie-changing endpoints, including login, against browser CSRF."""
    settings = Settings()
    origin = request.headers.get("origin")
    fetch_site = request.headers.get("sec-fetch-site")
    referer = request.headers.get("referer")
    if origin is None and referer is not None:
        try:
            parsed = urlsplit(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        except ValueError:
            origin = "null"
    if (
        fetch_site == "cross-site"
        or (origin is not None and origin not in settings.auth_allowed_origins)
        or (origin is None and fetch_site is not None and fetch_site != "same-origin")
    ):
        raise HTTPException(status_code=403, detail="Untrusted request origin")
    # CLI clients can omit browser headers. Origin checks are not authentication.


def prevent_auth_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def set_refresh_cookie(
    response: Response, raw_token: str, expires_at: datetime, settings: Settings,
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds())),
        # PostgreSQL may return timestamptz in the connection's local timezone.
        expires=expires_at.astimezone(timezone.utc),
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )
