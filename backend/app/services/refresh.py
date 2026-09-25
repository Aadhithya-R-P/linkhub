from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RefreshSession
from app.security import create_refresh_token, hash_refresh_token


class InvalidRefreshToken(Exception):
    pass


def start_refresh_session(
    session: Session, user_id: int, settings: Settings,
) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)
    raw_token = create_refresh_token()
    session.add(RefreshSession(
        user_id=user_id, expires_at=expires_at, token_hash=hash_refresh_token(raw_token),
    ))
    session.commit()
    return raw_token, expires_at


def _lock_refresh_session(session: Session, raw_token: str | None) -> RefreshSession | None:
    if raw_token is None or re.fullmatch(r"[A-Za-z0-9_-]{43}", raw_token) is None:
        return None
    # PostgreSQL READ COMMITTED rechecks this hash condition after a lock wait.
    # If another refresh replaced the hash, the old token no longer matches.
    return session.execute(
        select(RefreshSession).where(RefreshSession.token_hash == hash_refresh_token(raw_token))
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()


def rotate_refresh_token(session: Session, raw_token: str | None) -> tuple[int, str, datetime]:
    login_session = _lock_refresh_session(session, raw_token)
    now = datetime.now(timezone.utc)  # Check expiry AFTER any wait for the lock.
    if (
        login_session is None
        or login_session.revoked_at is not None
        or login_session.expires_at <= now
    ):
        session.rollback()
        raise InvalidRefreshToken

    replacement = create_refresh_token()
    login_session.token_hash = hash_refresh_token(replacement)
    user_id, expires_at = login_session.user_id, login_session.expires_at
    session.commit()  # Replace the hash atomically, then release the row lock.
    return user_id, replacement, expires_at


def revoke_refresh_session(session: Session, raw_token: str | None) -> None:
    login_session = _lock_refresh_session(session, raw_token)
    if login_session is not None and login_session.revoked_at is None:
        login_session.revoked_at = datetime.now(timezone.utc)
    session.commit()  # Logout is idempotent, including missing or unknown cookies.
