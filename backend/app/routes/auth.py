from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import Settings
from app.dependencies import get_current_user
from app.models import User
from app.schemas.auth import AccessTokenResponse, LoginRequest
from app.security import create_access_token
from app.schemas.user import UserCreate, UserRead
from app.services.auth import EmailAlreadyRegistered, authenticate_user, register_user
from app.auth_cookies import (
    REFRESH_COOKIE_NAME, clear_refresh_cookie, prevent_auth_caching,
    require_trusted_auth_origin, set_refresh_cookie,
)
from app.services.refresh import (
    InvalidRefreshToken, revoke_refresh_session, rotate_refresh_token, start_refresh_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, session: Annotated[Session, Depends(get_db)]):
    try:
        return register_user(session, data)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=409, detail="Email is already registered") from None


@router.post("/login", response_model=AccessTokenResponse,
             dependencies=[Depends(require_trusted_auth_origin)])
def login(data: LoginRequest, response: Response, session: Annotated[Session, Depends(get_db)]):
    user = authenticate_user(session, data.email, data.password.get_secret_value())
    if user is None:
        raise HTTPException(
            status_code=401, detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = Settings()
    raw_token, expires_at = start_refresh_session(session, user.id, settings)
    set_refresh_cookie(response, raw_token, expires_at, settings)
    prevent_auth_caching(response)
    return AccessTokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/refresh", response_model=AccessTokenResponse,
             dependencies=[Depends(require_trusted_auth_origin)])
def refresh(request: Request, response: Response, session: Annotated[Session, Depends(get_db)]):
    settings = Settings()
    try:
        user_id, raw_token, expires_at = rotate_refresh_token(
            session, request.cookies.get(REFRESH_COOKIE_NAME),
        )
    except InvalidRefreshToken:
        # Returning the response keeps the cookie-deletion headers on the 401.
        failure = JSONResponse(status_code=401, content={"detail": "Invalid or missing refresh token"})
        clear_refresh_cookie(failure, settings)
        prevent_auth_caching(failure)
        return failure
    set_refresh_cookie(response, raw_token, expires_at, settings)
    prevent_auth_caching(response)
    return AccessTokenResponse(
        access_token=create_access_token(user_id, settings),
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(require_trusted_auth_origin)])
def logout(request: Request, session: Annotated[Session, Depends(get_db)]):
    revoke_refresh_session(session, request.cookies.get(REFRESH_COOKIE_NAME))
    response = Response(status_code=204)
    clear_refresh_cookie(response, Settings())
    prevent_auth_caching(response)
    return response


@router.get("/me", response_model=UserRead)
def me(response: Response, user: Annotated[User, Depends(get_current_user)]):
    response.headers["Cache-Control"] = "no-store"
    return user
