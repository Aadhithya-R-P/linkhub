from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.auth_cookies import REFRESH_COOKIE_NAME
from app.config import Settings
from app.models import RefreshSession
from app.security import decode_access_token, hash_refresh_token
from app.services import refresh as refresh_service


@pytest.fixture(autouse=True)
def local_cookie_settings(monkeypatch):
    monkeypatch.setenv("REFRESH_COOKIE_SECURE", "false")
    monkeypatch.setenv("REFRESH_TOKEN_DAYS", "7")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", '["http://testserver"]')


def login(client):
    payload = {"email": f"{uuid4().hex}@example.com", "password": "long test password 123"}
    registered = client.post("/api/auth/register", json=payload)
    assert registered.status_code == 201
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 200
    return registered.json(), response, client.cookies.get(REFRESH_COOKIE_NAME)


def post_with_token(client, path, token):
    client.cookies.clear()
    headers = {} if token is None else {"Cookie": f"{REFRESH_COOKIE_NAME}={token}"}
    return client.post(path, headers=headers)


def test_login_cookie_and_hashed_storage(registration_client):
    client, connection = registration_client
    user, response, raw_token = login(client)
    assert set(response.json()) == {"access_token", "token_type", "expires_in"}
    assert raw_token not in response.text
    assert len(raw_token) == 43
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/api/auth" in cookie and "Domain=" not in cookie
    assert "expires=" in cookie and "Max-Age=" in cookie
    stored = connection.execute(select(RefreshSession.token_hash).where(
        RefreshSession.user_id == user["id"]
    )).scalar_one()
    assert stored != raw_token
    login_session = connection.execute(select(RefreshSession).where(
        RefreshSession.user_id == user["id"]
    )).one()
    assert login_session.revoked_at is None
    assert timedelta(days=6, hours=23) < login_session.expires_at - datetime.now(timezone.utc) <= timedelta(days=7)


def test_secure_cookie_setting(registration_client, monkeypatch):
    client, _ = registration_client
    monkeypatch.setenv("REFRESH_COOKIE_SECURE", "true")
    _, response, _ = login(client)
    assert "Secure" in response.headers["set-cookie"]
    response = client.post("/api/auth/logout")
    assert "Secure" in response.headers["set-cookie"]


def test_rotation_preserves_expiry_and_issues_working_access_token(registration_client):
    client, connection = registration_client
    user, _, first = login(client)
    expires_at = connection.execute(select(RefreshSession.expires_at).where(
        RefreshSession.user_id == user["id"]
    )).scalar_one()
    response = client.post("/api/auth/refresh")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    second = client.cookies.get(REFRESH_COOKIE_NAME)
    assert second != first
    access_token = response.json()["access_token"]
    assert decode_access_token(access_token, Settings()) == user["id"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}).status_code == 200
    stored_hashes = connection.execute(select(RefreshSession.token_hash).where(
        RefreshSession.user_id == user["id"]
    )).scalars().all()
    assert stored_hashes == [hash_refresh_token(second)]
    assert connection.execute(select(RefreshSession.expires_at).where(
        RefreshSession.user_id == user["id"]
    )).scalar_one() == expires_at
    assert client.post("/api/auth/refresh").status_code == 200


def test_old_token_is_rejected_without_revoking_current_or_another_login(registration_client):
    client, connection = registration_client
    user, _, first = login(client)
    assert client.post("/api/auth/refresh").status_code == 200
    successor = client.cookies.get(REFRESH_COOKIE_NAME)
    another_login = client.post("/api/auth/login", json={
        "email": user["email"], "password": "long test password 123",
    })
    assert another_login.status_code == 200
    independent = client.cookies.get(REFRESH_COOKIE_NAME)
    assert post_with_token(client, "/api/auth/refresh", first).status_code == 401
    assert post_with_token(client, "/api/auth/refresh", successor).status_code == 200
    assert post_with_token(client, "/api/auth/refresh", independent).status_code == 200
    revoked = connection.execute(select(RefreshSession.revoked_at).where(
        RefreshSession.user_id == user["id"]
    )).scalars().all()
    assert revoked == [None, None]


@pytest.mark.parametrize("token", [None, "malformed", "a" * 43])
def test_invalid_refresh_clears_cookie_without_echoing_token(registration_client, token):
    client, _ = registration_client
    response = post_with_token(client, "/api/auth/refresh", token)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing refresh token"}
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert response.headers["Cache-Control"] == "no-store"
    assert client.cookies.get(REFRESH_COOKIE_NAME) is None


def test_expired_session_cannot_refresh(registration_client):
    client, connection = registration_client
    user, _, _ = login(client)
    connection.execute(update(RefreshSession).where(RefreshSession.user_id == user["id"]).values(
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    ))
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_revokes_current_token_but_existing_access_still_works(registration_client):
    client, _ = registration_client
    _, response, first = login(client)
    access_token = response.json()["access_token"]
    assert client.post("/api/auth/refresh").status_code == 200
    current = client.cookies.get(REFRESH_COOKIE_NAME)
    response = post_with_token(client, "/api/auth/logout", current)
    assert response.status_code == 204 and response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert response.headers["Cache-Control"] == "no-store"
    assert post_with_token(client, "/api/auth/refresh", current).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}).status_code == 200
    assert client.post("/api/auth/logout").status_code == 204


def test_logout_with_old_token_does_not_revoke_current_token(registration_client):
    client, _ = registration_client
    _, _, first = login(client)
    assert client.post("/api/auth/refresh").status_code == 200
    current = client.cookies.get(REFRESH_COOKIE_NAME)
    assert post_with_token(client, "/api/auth/logout", first).status_code == 204
    assert post_with_token(client, "/api/auth/refresh", current).status_code == 200


def test_logout_does_not_revoke_another_login(registration_client):
    client, _ = registration_client
    user, _, first = login(client)
    assert client.post("/api/auth/login", json={
        "email": user["email"], "password": "long test password 123",
    }).status_code == 200
    second = client.cookies.get(REFRESH_COOKIE_NAME)
    assert post_with_token(client, "/api/auth/logout", first).status_code == 204
    assert post_with_token(client, "/api/auth/refresh", first).status_code == 401
    assert post_with_token(client, "/api/auth/refresh", second).status_code == 200


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout"])
@pytest.mark.parametrize("headers", [
    {"Origin": "https://attacker.example"},
    {"Origin": "http://testserver.attacker.example"},
    {"Origin": "null"},
    {"Referer": "https://attacker.example/form"},
    {"Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "same-site"},
])
def test_untrusted_browser_requests_are_rejected(registration_client, path, headers):
    client, _ = registration_client
    _, _, token = login(client)
    response = client.post(path, headers=headers, json={
        "email": "someone@example.com", "password": "irrelevant password",
    })
    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    # Rejection must not consume or revoke the victim's token.
    assert post_with_token(client, "/api/auth/refresh", token).status_code == 200


def test_allowed_browser_origin(registration_client):
    client, _ = registration_client
    login(client)
    assert client.post("/api/auth/refresh", headers={
        "Origin": "http://testserver", "Sec-Fetch-Site": "same-origin",
    }).status_code == 200


def test_failed_rotation_preserves_current_hash(registration_client, monkeypatch):
    client, connection = registration_client
    user, _, first = login(client)
    _, _, another_token = login(client)
    # Force the hash UPDATE to violate another login's unique token hash.
    with monkeypatch.context() as patch:
        patch.setattr(refresh_service, "create_refresh_token", lambda: another_token)
        with pytest.raises(IntegrityError):
            post_with_token(client, "/api/auth/refresh", first)
    assert connection.execute(select(RefreshSession.token_hash).where(
        RefreshSession.user_id == user["id"]
    )).scalar_one() == hash_refresh_token(first)
    assert post_with_token(client, "/api/auth/refresh", first).status_code == 200
