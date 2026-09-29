from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.links import get_redirect_destination

router = APIRouter(prefix="/r", tags=["redirects"])


@router.get("/{short_code}", response_class=RedirectResponse, status_code=302)
def redirect(short_code: str, session: Annotated[Session, Depends(get_db)]):
    destination = get_redirect_destination(session, short_code)
    # Do not retain redirects or failures after an owner changes a link.
    headers = {"Cache-Control": "no-store"}
    if destination is None:
        raise HTTPException(status_code=404, detail="Link not found", headers=headers)
    return RedirectResponse(url=destination, status_code=302, headers=headers)
