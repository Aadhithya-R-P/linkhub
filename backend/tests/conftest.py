import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db, get_engine
from app.main import app


@pytest.fixture
def registration_client():
    if os.getenv("LINKHUB_TEST_DB") != "1":
        pytest.skip("requires migrated local PostgreSQL")
    with get_engine().connect() as connection:
        transaction = connection.begin()
        def override_db():
            # Endpoint commits release a savepoint, not the outer test transaction.
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                yield session
        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app) as client:
                yield client, connection
        finally:
            app.dependency_overrides.pop(get_db, None)
            transaction.rollback()

