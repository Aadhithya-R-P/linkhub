from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import delete

from app.config import Settings
from app.models import User
from app.security import create_access_token, decode_access_token


def register(client):
    payload = {"email": f"{uuid4().hex}@example.com", "password": "long test password 123"}
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    return payload, response.json()


def test_login_then_me(registration_client):
    client, _ = registration_client
    payload, user = register(client)
    payload["email"] = payload["email"].upper()
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == Settings().access_token_minutes * 60
    assert decode_access_token(body["access_token"], Settings()) == user["id"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert response.status_code == 200
    assert response.json() == user
    assert "password_hash" not in response.json()


def test_wrong_password_and_unknown_email_match(registration_client):
    client, _ = registration_client
    payload, _ = register(client)
    payload["password"] = "wrong password"
    wrong = client.post("/api/auth/login", json=payload)
    payload["email"] = f"{uuid4().hex}@example.com"
    unknown = client.post("/api/auth/login", json=payload)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer garbage"])
def test_me_requires_valid_bearer(registration_client, authorization):
    client, _ = registration_client
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("fault", ["expired", "signature", "issuer", "audience", "missing_exp", "type", "subject", "algorithm", "tampered"])
def test_me_rejects_invalid_claims_and_signatures(registration_client, fault):
    client, _ = registration_client
    _, user = register(client)
    settings = Settings()
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user["id"]), "iat": now - timedelta(minutes=30),
              "exp": now + timedelta(minutes=5), "iss": "linkhub", "aud": "linkhub-api", "token_type": "access"}
    key = settings.jwt_secret.get_secret_value()
    algorithm = "HS256"
    if fault == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    elif fault == "signature":
        key = "different-test-key-" * 4
    elif fault == "issuer":
        claims["iss"] = "other-app"
    elif fault == "audience":
        claims["aud"] = "other-api"
    elif fault == "missing_exp":
        del claims["exp"]
    elif fault == "type":
        claims["token_type"] = "refresh"
    elif fault == "subject":
        claims["sub"] = "9999999999999999999999"
    elif fault == "algorithm":
        algorithm = "HS384"
        key = "different-test-key-" * 4
    token = jwt.encode(claims, key, algorithm=algorithm)
    if fault == "tampered":
        header, _, signature = token.split(".")
        claims["sub"] = str(user["id"] + 1)
        changed = jwt.encode(claims, key, algorithm=algorithm).split(".")[1]
        token = f"{header}.{changed}.{signature}"
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_deleted_user_token_rejected(registration_client):
    client, connection = registration_client
    _, user = register(client)
    token = create_access_token(user["id"], Settings())
    connection.execute(delete(User).where(User.id == user["id"]))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
