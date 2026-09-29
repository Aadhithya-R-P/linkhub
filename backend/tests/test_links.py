from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select, update

from app.models import Link, User
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


def insert_owned_links(connection, user_id, count):
    return [connection.execute(insert(Link).values(
        user_id=user_id, destination_url=f"https://example.com/{index}",
    ).returning(Link.id)).scalar_one() for index in range(count)]


def test_list_empty(link_owner):
    client, _, _, headers = link_owner
    response = client.get("/api/links", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_before_id": None}
    assert response.headers["cache-control"] == "no-store"


def test_list_pagination_and_ownership(link_owner):
    client, connection, user_id, headers = link_owner
    other_id = connection.execute(insert(User).values(
        email=f"{uuid4().hex}@example.com", password_hash="unused",
    ).returning(User.id)).scalar_one()
    ids = insert_owned_links(connection, user_id, 2)
    other_link = insert_owned_links(connection, other_id, 1)[0]
    ids += insert_owned_links(connection, user_id, 3)
    connection.execute(update(Link).where(Link.id == ids[-1]).values(is_active=False))
    connection.execute(update(Link).where(Link.id == ids[-2]).values(
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    seen = []
    params = {"limit": 2}
    for expected_size in [2, 2, 1]:
        response = client.get("/api/links", params=params, headers=headers)
        assert response.status_code == 200
        page = response.json()
        assert len(page["items"]) == expected_size
        for item in page["items"]:
            assert set(item) == {"id", "short_code", "destination_url", "created_at", "is_active", "expires_at"}
            assert item["short_code"] == encode_link_id(item["id"])
        seen.extend(item["id"] for item in page["items"])
        if expected_size == 2:
            assert page["next_before_id"] == page["items"][-1]["id"]
            params["before_id"] = page["next_before_id"]
        else:
            assert page["next_before_id"] is None
    assert seen == ids[::-1]
    # A different user's ID is only a numeric boundary, never an ownership selector.
    page = client.get("/api/links", params={"before_id": other_link}, headers=headers).json()
    assert [item["id"] for item in page["items"]] == ids[:2][::-1]


def test_list_cursor_survives_new_insert_and_deleted_boundary(link_owner):
    client, connection, user_id, headers = link_owner
    ids = insert_owned_links(connection, user_id, 4)
    page = client.get("/api/links?limit=2", headers=headers).json()
    assert [item["id"] for item in page["items"]] == ids[2:][::-1]
    cursor = page["next_before_id"]
    insert_owned_links(connection, user_id, 1)
    connection.execute(delete(Link).where(Link.id == cursor))
    page = client.get("/api/links", params={"limit": 2, "before_id": cursor}, headers=headers).json()
    assert [item["id"] for item in page["items"]] == ids[:2][::-1]
    assert page["next_before_id"] is None


def test_list_default_and_maximum_page_sizes(link_owner):
    client, connection, user_id, headers = link_owner
    ids = insert_owned_links(connection, user_id, 101)
    default = client.get("/api/links", headers=headers).json()
    assert len(default["items"]) == 20
    assert default["next_before_id"] == ids[-20]
    maximum = client.get("/api/links?limit=100", headers=headers).json()
    assert len(maximum["items"]) == 100
    assert maximum["next_before_id"] == ids[-100]
    end = client.get("/api/links?before_id=1", headers=headers).json()
    assert end == {"items": [], "next_before_id": None}


@pytest.mark.parametrize("query", [
    "limit=0", "limit=-1", "limit=101", "limit=abc", "limit=1.5",
    "before_id=0", "before_id=-1", "before_id=2147483648", "before_id=abc",
])
def test_list_rejects_invalid_pagination(link_owner, query):
    client, _, _, headers = link_owner
    assert client.get(f"/api/links?{query}", headers=headers).status_code == 422


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}])
def test_list_requires_access_token(link_owner, headers):
    client, _, _, _ = link_owner
    response = client.get("/api/links", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
