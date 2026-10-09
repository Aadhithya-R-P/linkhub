from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ClickEvent, Link
from app.schemas.link import LinkCreate, LinkUpdate
from app.short_codes import decode_short_code
from app.services.clicks import record_click
from app.redirect_cache import get_redirect_cache


def get_click_counts(session: Session, link_ids: list[int]) -> dict[int, int]:
    """Count events only for already-authorized links, in one grouped query."""
    if not link_ids:
        return {}
    statement = select(ClickEvent.link_id, func.count()).where(
        ClickEvent.link_id.in_(link_ids)
    ).group_by(ClickEvent.link_id)
    return dict(session.execute(statement).all())


def list_links(
    session: Session, user_id: int, limit: int, before_id: int | None,
) -> tuple[list[Link], int | None]:
    statement = select(Link).where(Link.user_id == user_id)
    if before_id is not None:
        statement = statement.where(Link.id < before_id)
    #this is keyset pagination, there's also Offset pagination but we haven't used it here
    # One extra row tells us whether another page exists, without a COUNT query.
    rows = list(session.scalars(statement.order_by(Link.id.desc()).limit(limit + 1)))
    items = rows[:limit]
    next_before_id = items[-1].id if len(rows) > limit else None
    return items, next_before_id


def create_link(session: Session, data: LinkCreate, user_id: int) -> Link:
    link = Link(user_id=user_id, destination_url=str(data.destination_url))
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def delete_link(session: Session, link_id: int, user_id: int) -> bool:
    # Check ownership and remove the row in one database statement.
    statement = delete(Link).where(
        Link.id == link_id, Link.user_id == user_id,
    ).returning(Link.id)
    deleted_id = session.execute(statement).scalar_one_or_none()
    session.commit()
    if deleted_id is not None:
        get_redirect_cache().invalidate(link_id)
    return deleted_id is not None


def get_redirect_destination(session: Session, short_code: str) -> str | None:
    """Resolve an available link and record its redirect request best-effort."""
    try:
        link_id = decode_short_code(short_code)
    except ValueError:
        return None
    cache = get_redirect_cache()
    cached = cache.get(link_id)
    if cached is not None:
        if cached.expires_at is not None and cached.expires_at <= datetime.now(timezone.utc):
            return None
        destination = str(cached.destination_url)
        record_click(session, link_id)
        return destination
    link = session.get(Link, link_id)
    if link is None or not link.is_active:
        return None
    if link.expires_at is not None and link.expires_at <= datetime.now(timezone.utc):
        return None
    # Commit/rollback expires ORM attributes. Keep the destination before recording
    # so even a failed analytics write cannot trigger another database read.
    destination = link.destination_url
    cache.put(link_id, destination, link.expires_at)
    record_click(session, link_id)
    return destination


def update_link(link_id: int, session: Session, data: LinkUpdate, user_id: int) -> Link | None:
    statement = select(Link).where(Link.user_id == user_id).where(Link.id == link_id)
    row = session.execute(statement).scalar_one_or_none()
    if row is None:
        return None
    # Presence matters: an explicit null clears expiration, but omission preserves it.
    if "destination_url" in data.model_fields_set:
        row.destination_url = str(data.destination_url)
    if "is_active" in data.model_fields_set:
        row.is_active = data.is_active
    if "expires_at" in data.model_fields_set:
        row.expires_at = (
            data.expires_at.astimezone(timezone.utc) if data.expires_at is not None else None
        )
    session.commit()
    get_redirect_cache().invalidate(link_id)
    session.refresh(row)
    return row
