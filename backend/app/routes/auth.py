from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import Settings
from app.dependencies import get_current_user
from app.models import User
from app.schemas.auth import AccessTokenResponse, LoginRequest
from app.security import create_access_token
from app.schemas.user import UserCreate, UserRead
from app.services.auth import EmailAlreadyRegistered, authenticate_user, register_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, session: Annotated[Session, Depends(get_db)]):
    try:
        return register_user(session, data)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=409, detail="Email is already registered") from None


@router.post("/login", response_model=AccessTokenResponse)
def login(data: LoginRequest, response: Response, session: Annotated[Session, Depends(get_db)]):
    user = authenticate_user(session, data.email, data.password.get_secret_value())
    if user is None:
        raise HTTPException(
            status_code=401, detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = Settings()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return AccessTokenResponse(
        access_token=create_access_token(user.id, settings),
        expires_in=settings.access_token_minutes * 60,
    )


@router.get("/me", response_model=UserRead)
def me(response: Response, user: Annotated[User, Depends(get_current_user)]):
    response.headers["Cache-Control"] = "no-store"
    return user
