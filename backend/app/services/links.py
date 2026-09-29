from sqlalchemy.orm import Session

from app.models import Link
from app.schemas.link import LinkCreate


def create_link(session: Session, data: LinkCreate, user_id: int) -> Link:
    link = Link(user_id=user_id, destination_url=str(data.destination_url))
    session.add(link)
    session.commit()
    session.refresh(link)
    return link
