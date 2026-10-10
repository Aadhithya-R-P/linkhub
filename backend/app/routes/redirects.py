from typing import Annotated
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.links import get_redirect_destination

router = APIRouter(prefix="/r", tags=["redirects"])
UNAVAILABLE_PAGE = (Path(__file__).resolve().parents[1] / "pages" / "link_unavailable.html").read_text(encoding="utf-8")


@router.get("/{short_code}", response_class=RedirectResponse, status_code=302,
            responses={404: {"content": {"text/html": {}}, "description": "Link unavailable"}})
def redirect(short_code: str, session: Annotated[Session, Depends(get_db)]):
    destination = get_redirect_destination(session, short_code)
    # Do not retain redirects or failures after an owner changes a link.
    headers = {"Cache-Control": "no-store"}
    if destination is None:
        return HTMLResponse(UNAVAILABLE_PAGE, status_code=404, headers=headers)
    return RedirectResponse(url=destination, status_code=302, headers=headers)
