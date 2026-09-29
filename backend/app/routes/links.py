from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.link import LinkCreate, LinkRead
from app.services.links import create_link
from app.short_codes import encode_link_id

router = APIRouter(prefix="/api/links", tags=["links"])


@router.post("", response_model=LinkRead, status_code=status.HTTP_201_CREATED)
def create(
    data: LinkCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
):
    link = create_link(session, data, user.id)
    return LinkRead(
        id=link.id,
        short_code=encode_link_id(link.id),
        destination_url=link.destination_url,
        created_at=link.created_at,
        is_active=link.is_active,
        expires_at=link.expires_at,
    )
