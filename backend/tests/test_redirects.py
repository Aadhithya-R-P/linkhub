from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, insert, select, text, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models import ClickEvent, Link, User
from app.services import links as links_service
from app.short_codes import MAX_LINK_ID, decode_short_code, encode_link_id


@pytest.mark.parametrize("link_id", [1, 9, 10, 35, 36, 61, 62, 3843, 3844, MAX_LINK_ID])
def test_decode_round_trip(link_id):
    assert decode_short_code(encode_link_id(link_id)) == link_id


def test_decode_is_case_sensitive():
    assert decode_short_code("A") == 10
    assert decode_short_code("a") == 36


@pytest.mark.parametrize("code", ["", "0", "01", "-1", "a_b", "a b", "é", "１", "2LKcb2", "zzzzzz", "1" * 1000])
def test_decode_rejects_noncanonical_or_out_of_range_codes(code):
    with pytest.raises(ValueError):
        decode_short_code(code)


@pytest.mark.parametrize("code", ["0", "01", "-1", "a_b", "é", "2LKcb2", "zzzzzz", "1" * 1000])
def test_malformed_redirect_does_not_query_database(code):
    class UnusedSession:
        def get(self, *args):
            pytest.fail("Malformed code must not query PostgreSQL")

    def override_db():
        yield UnusedSession()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.get(f"/r/{code}", follow_redirects=False)
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")
        assert "This link is unavailable" in response.text
        assert response.headers["cache-control"] == "no-store"
        assert "location" not in response.headers
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def redirect_link(registration_client):
    client, connection = registration_client
    user_id = connection.execute(insert(User).values(
        email=f"{uuid4().hex}@example.com", password_hash="unused in public redirect tests",
    ).returning(User.id)).scalar_one()
    destination = "https://example.com/articles?topic=python&sort=new#details"
    link_id = connection.execute(insert(Link).values(
        user_id=user_id, destination_url=destination,
    ).returning(Link.id)).scalar_one()
    return client, connection, link_id, destination


def test_public_redirect_preserves_destination(redirect_link):
    client, _, link_id, destination = redirect_link
    # This client has never logged in: no access token or refresh cookie.
    response = client.get(f"/r/{encode_link_id(link_id)}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == destination
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("state", ["missing", "inactive", "expired"])
def test_unavailable_links_return_same_404(redirect_link, state):
    client, connection, link_id, _ = redirect_link
    if state == "missing":
        connection.execute(delete(Link).where(Link.id == link_id))
    elif state == "inactive":
        connection.execute(update(Link).where(Link.id == link_id).values(is_active=False))
    else:
        connection.execute(update(Link).where(Link.id == link_id).values(
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        ))
    response = client.get(f"/r/{encode_link_id(link_id)}", follow_redirects=False)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "This link is unavailable" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "location" not in response.headers
    assert connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == link_id)).all() == []


def test_each_successful_get_records_a_timestamped_click(redirect_link):
    client, connection, link_id, _ = redirect_link
    path = f"/r/{encode_link_id(link_id)}"
    for _ in range(2):
        assert client.get(path, follow_redirects=False).status_code == 302
    rows = connection.execute(select(ClickEvent).where(ClickEvent.link_id == link_id)).all()
    assert len(rows) == 2
    assert rows[0].id != rows[1].id
    assert all(row.clicked_at.tzinfo is not None for row in rows)
    assert client.head(path).status_code == 405
    assert len(connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == link_id)).all()) == 2


def test_analytics_database_failure_rolls_back_but_still_redirects(redirect_link, caplog):
    client, connection, link_id, destination = redirect_link

    def fail_insert(mapper, target_connection, target):
        # A real PostgreSQL error aborts the transaction until rollback.
        target_connection.execute(text("SELECT 1 / 0"))

    event.listen(ClickEvent, "before_insert", fail_insert)
    try:
        response = client.get(f"/r/{encode_link_id(link_id)}", follow_redirects=False)
    finally:
        event.remove(ClickEvent, "before_insert", fail_insert)
    assert response.status_code == 302
    assert response.headers["location"] == destination
    assert response.headers["cache-control"] == "no-store"
    assert connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == link_id)).all() == []
    assert "Click event could not be recorded" in caplog.text
    assert "SELECT 1 / 0" not in caplog.text
    assert destination not in caplog.text
    # Recording recovers on the next request.
    assert client.get(f"/r/{encode_link_id(link_id)}", follow_redirects=False).status_code == 302
    assert len(connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == link_id)).all()) == 1


def test_hard_delete_cascades_only_its_click_events(redirect_link):
    client, connection, link_id, _ = redirect_link
    owner = connection.execute(select(Link.user_id).where(Link.id == link_id)).scalar_one()
    other_id = connection.execute(insert(Link).values(
        user_id=owner, destination_url="https://example.org/",
    ).returning(Link.id)).scalar_one()
    for target_id in (link_id, other_id):
        assert client.get(f"/r/{encode_link_id(target_id)}", follow_redirects=False).status_code == 302
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        assert links_service.delete_link(session, link_id, owner)
    assert connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == link_id)).all() == []
    assert len(connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == other_id)).all()) == 1


@pytest.mark.parametrize("offset, expected_status", [(-1, 404), (0, 404), (1, 302)])
def test_expiration_boundary_with_timezone(redirect_link, monkeypatch, offset, expected_status):
    client, connection, link_id, _ = redirect_link
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz)

    monkeypatch.setattr(links_service, "datetime", FrozenDatetime)
    expires_at = (now + timedelta(seconds=offset)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    connection.execute(update(Link).where(Link.id == link_id).values(expires_at=expires_at))
    response = client.get(f"/r/{encode_link_id(link_id)}", follow_redirects=False)
    assert response.status_code == expected_status


def test_next_request_observes_disable_and_destination_change(redirect_link):
    client, connection, link_id, _ = redirect_link
    path = f"/r/{encode_link_id(link_id)}"
    assert client.get(path, follow_redirects=False).status_code == 302
    connection.execute(update(Link).where(Link.id == link_id).values(is_active=False))
    assert client.get(path, follow_redirects=False).status_code == 404
    connection.execute(update(Link).where(Link.id == link_id).values(
        is_active=True, destination_url="http://example.org/new",
    ))
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "http://example.org/new"
