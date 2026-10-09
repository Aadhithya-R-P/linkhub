import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ClickEvent

logger = logging.getLogger(__name__)


def record_click(session: Session, link_id: int) -> None:
    """Best-effort recording: analytics failures must not block a valid redirect."""
    try:
        session.add(ClickEvent(link_id=link_id))
        session.commit()
    except SQLAlchemyError:
        try:
            session.rollback()
        except SQLAlchemyError:
            # A lost connection can also prevent rollback; the request's session
            # is closed by get_db. We already have the redirect destination.
            pass
        # Database exceptions can include SQL parameters; do not log their contents.
        logger.warning("Click event could not be recorded; redirect will continue.")
