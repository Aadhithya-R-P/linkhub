from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Link
from app.schemas.link import LinkCreate
from app.short_codes import decode_short_code


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


def get_redirect_destination(session: Session, short_code: str) -> str | None:
    try:
        link_id = decode_short_code(short_code)
    except ValueError:
        return None
    link = session.get(Link, link_id)
    if link is None or not link.is_active:
        return None
    if link.expires_at is not None and link.expires_at <= datetime.now(timezone.utc):
        return None
    return link.destination_url
