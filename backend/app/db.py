from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.config import Settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = Settings()
    return create_engine(
        settings.get_database_url(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def get_db() -> Iterator[Session]:
    # One session per request. Services will explicitly commit their writes.
    with Session(get_engine()) as session:
        yield session
