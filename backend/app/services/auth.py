from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.schemas.user import UserCreate
from app.security import get_dummy_password_hash, hash_password, verify_password


class EmailAlreadyRegistered(Exception):
    pass


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    # Even unknown emails perform a password check to reduce timing differences.
    password_hash = user.password_hash if user is not None else get_dummy_password_hash()
    valid = verify_password(password, password_hash)
    return user if user is not None and valid else None


def register_user(session: Session, data: UserCreate) -> User:
    user = User(
        email=data.email,
        display_name=data.display_name,
        password_hash=hash_password(data.password.get_secret_value()),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # Handle only our email uniqueness violation, not unrelated DB errors.
        diagnostic = getattr(exc.orig, "diag", None)
        if (
            getattr(exc.orig, "sqlstate", None) == "23505"
            and getattr(diagnostic, "constraint_name", None) == "users_email_key"
        ):
            raise EmailAlreadyRegistered from exc
        raise
    session.refresh(user)
    return user
