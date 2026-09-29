from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models import Link, User
from app.schemas.link import LinkCreate, LinkPage, LinkRead, LinkUpdate
from app.services.links import create_link, list_links, update_link
from app.short_codes import MAX_LINK_ID, encode_link_id

router = APIRouter(prefix="/api/links", tags=["links"])


def link_response(link: Link) -> LinkRead:
    return LinkRead(
        id=link.id,
        short_code=encode_link_id(link.id),
        destination_url=link.destination_url,
        created_at=link.created_at,
        is_active=link.is_active,
        expires_at=link.expires_at,
    )


@router.get("", response_model=LinkPage)
def list_owned_links(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before_id: Annotated[int | None, Query(ge=1, le=MAX_LINK_ID)] = None,
):
    items, next_before_id = list_links(session, user.id, limit, before_id)
    response.headers["Cache-Control"] = "no-store"
    return LinkPage(
        items=[link_response(link) for link in items],
        next_before_id=next_before_id,
    )


@router.post("", response_model=LinkRead, status_code=status.HTTP_201_CREATED)
def create(
    data: LinkCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
):
    link = create_link(session, data, user.id)
    return link_response(link)

@router.patch("/{link_id}", response_model=LinkRead, status_code=status.HTTP_200_OK)
def update(
    link_id: Annotated[int, Path(ge=1, le=MAX_LINK_ID)],
    data: LinkUpdate,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
):
    link = update_link(link_id, session, data, user.id)
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    response.headers["Cache-Control"] = "no-store"
    return link_response(link)
