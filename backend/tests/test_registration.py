from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models import User
from app.security import verify_password



def test_registration_stores_hash_and_returns_only_public_fields(registration_client):
    client, connection = registration_client
    email = f"{uuid4().hex}@example.com"
    password = "long test password 123"
    response = client.post("/api/auth/register", json={"email": email.upper(), "password": password})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "display_name", "created_at"}
    assert body["email"] == email
    stored_hash = connection.execute(select(User.password_hash).where(User.id == body["id"])).scalar_one()
    assert stored_hash != password
    assert verify_password(password, stored_hash)
    assert not verify_password("wrong password", stored_hash)


def test_duplicate_email_and_recovery(registration_client):
    client, _ = registration_client
    email = f"{uuid4().hex}@example.com"
    payload = {"email": email, "password": "long test password 123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    payload["email"] = email.upper()
    assert client.post("/api/auth/register", json=payload).status_code == 409
    payload["email"] = f"{uuid4().hex}@example.com"
    assert client.post("/api/auth/register", json=payload).status_code == 201


@pytest.mark.parametrize("changes", [
    {"email": "invalid"}, {"password": "x7!q"}, {"password": "a" * 129},
    {"display_name": "a" * 101}, {"user_id": 5},
])
def test_invalid_registration_does_not_echo_password(changes):
    def unused_db():
        yield None
    app.dependency_overrides[get_db] = unused_db
    payload = {"email": "alex@example.com", "password": "long test password 123"}
    payload.update(changes)
    try:
        with TestClient(app) as client:
            response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 422
        assert payload["password"] not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)
