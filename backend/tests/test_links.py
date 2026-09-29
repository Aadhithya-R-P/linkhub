from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import Link
from app.short_codes import MAX_LINK_ID, encode_link_id


@pytest.mark.parametrize("link_id, code", [
    (1, "1"), (9, "9"), (10, "A"), (35, "Z"), (36, "a"),
    (61, "z"), (62, "10"), (3843, "zz"), (3844, "100"),
    (MAX_LINK_ID, "2LKcb1"),
])
def test_base62_known_codes(link_id, code):
    assert encode_link_id(link_id) == code


@pytest.mark.parametrize("link_id", [0, -1, MAX_LINK_ID + 1])
def test_base62_rejects_out_of_range_ids(link_id):
    with pytest.raises(ValueError):
        encode_link_id(link_id)


@pytest.fixture
def link_owner(registration_client):
    client, connection = registration_client
    credentials = {"email": f"{uuid4().hex}@example.com", "password": "long test password 123"}
    registered = client.post("/api/auth/register", json=credentials)
    assert registered.status_code == 201
    login = client.post("/api/auth/login", json=credentials)
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return client, connection, registered.json()["id"], headers


def test_create_link_persists_owner_and_defaults(link_owner):
    client, connection, user_id, headers = link_owner
    destination = "https://example.com/articles?q=python#details"
    response = client.post("/api/links", json={"destination_url": destination}, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "short_code", "destination_url", "created_at", "is_active", "expires_at"}
    assert body["destination_url"] == destination
    assert body["short_code"] == encode_link_id(body["id"])
    assert body["is_active"] is True
    assert body["expires_at"] is None
    assert body["created_at"]
    stored = connection.execute(select(Link.__table__).where(Link.id == body["id"])).mappings().one()
    assert stored["user_id"] == user_id
    assert stored["destination_url"] == destination
    # Repeated destinations are independent links, not a uniqueness conflict.
    second = client.post("/api/links", json={"destination_url": destination}, headers=headers)
    assert second.status_code == 201
    assert second.json()["short_code"] != body["short_code"]


def test_http_url_is_normalized(link_owner):
    client, _, _, headers = link_owner
    response = client.post("/api/links", json={"destination_url": "http://EXAMPLE.com"}, headers=headers)
    assert response.status_code == 201
    assert response.json()["destination_url"] == "http://example.com/"


@pytest.mark.parametrize("payload", [
    {}, {"destination_url": None}, {"destination_url": "not a URL"},
    {"destination_url": "/relative"}, {"destination_url": "ftp://example.com/file"},
    {"destination_url": "javascript:alert(1)"},
    {"destination_url": "https://user:password@example.com"},
    {"destination_url": "https://example.com/" + "x" * 2083},
    {"destination_url": "https://example.com", "user_id": 123},
    {"destination_url": "https://example.com", "is_active": False},
    {"destination_url": "https://example.com", "expires_at": "2030-01-01T00:00:00Z"},
    {"destination_url": "https://example.com", "short_code": "custom"},
])
def test_invalid_input_creates_no_link(link_owner, payload):
    client, connection, _, headers = link_owner
    count = select(func.count()).select_from(Link)
    before = connection.execute(count).scalar_one()
    response = client.post("/api/links", json=payload, headers=headers)
    assert response.status_code == 422
    assert connection.execute(count).scalar_one() == before
    assert all("input" not in error for error in response.json()["detail"])


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}])
def test_create_requires_access_token(link_owner, headers):
    # Login left a refresh cookie on this client: that cookie is not authorization.
    client, connection, _, _ = link_owner
    count = select(func.count()).select_from(Link)
    before = connection.execute(count).scalar_one()
    response = client.post("/api/links", json={"destination_url": "https://example.com"}, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert connection.execute(count).scalar_one() == before
