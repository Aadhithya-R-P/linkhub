from datetime import datetime, timedelta, timezone
import os
import time
from unittest.mock import Mock
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import ConnectionError, TimeoutError
from sqlalchemy import insert, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models import ClickEvent, Link, User
from app.redirect_cache import CachedRedirect, RedirectCache
from app.schemas.link import LinkUpdate
from app.services import links as service
from app.short_codes import encode_link_id


def test_fixed_ttl_and_cached_expiration():
    client = Mock()
    cache = RedirectCache(client)
    expires = datetime.now(timezone.utc) + timedelta(seconds=2)
    cache.put(1, "https://example.com/", expires)
    args, kwargs = client.set.call_args
    assert kwargs == {"ex": 30}
    assert CachedRedirect.model_validate_json(args[1]).expires_at == expires
    client.get.return_value = args[1].encode()
    assert cache.get(1).expires_at == expires


@pytest.mark.parametrize("raw", [b"not json", b"{}", b"null", b'[]',
    b'{"destination_url":"javascript:alert(1)","expires_at":null}',
    b'{"destination_url":"https://example.com/","expires_at":"2027-01-01T00:00:00"}'])
def test_malformed_entries_are_misses(raw):
    client = Mock()
    client.get.return_value = raw
    assert RedirectCache(client).get(1) is None


@pytest.mark.parametrize("failure", [ConnectionError, TimeoutError])
def test_redis_failures_are_best_effort_and_logs_hide_details(failure, caplog):
    client = Mock()
    for method in (client.get, client.set, client.delete):
        method.side_effect = failure("private-connection-details")
    cache = RedirectCache(client)
    assert cache.get(1) is None
    cache.put(1, "https://example.com/", None)
    cache.invalidate(1)
    assert "private-connection-details" not in caplog.text
    assert "invalidation failed" in caplog.text


def test_disabled_cache_does_not_connect(monkeypatch):
    from app import redirect_cache
    monkeypatch.setenv("REDIRECT_CACHE_ENABLED", "false")
    monkeypatch.setattr(redirect_cache.Redis, "from_url", lambda *a, **kw: pytest.fail("must not connect"))
    redirect_cache.get_redirect_cache.cache_clear()
    try:
        cache = redirect_cache.get_redirect_cache()
        assert cache.get(1) is None
        cache.put(1, "https://example.com/", None)
        cache.invalidate(1)
    finally:
        redirect_cache.get_redirect_cache.cache_clear()


@pytest.fixture
def cached_link(registration_client, monkeypatch):
    client, connection = registration_client
    owner = connection.execute(insert(User).values(
        email=f"{uuid4().hex}@example.com", password_hash="unused",
    ).returning(User.id)).scalar_one()
    link_id = connection.execute(insert(Link).values(
        user_id=owner, destination_url="https://example.com/original",
    ).returning(Link.id)).scalar_one()
    values = {}
    redis = Mock()
    redis.get.side_effect = lambda key: values.get(key)
    redis.set.side_effect = lambda key, value, **kwargs: values.__setitem__(key, value)
    redis.delete.side_effect = lambda key: values.pop(key, None)
    cache = RedirectCache(redis)
    monkeypatch.setattr(service, "get_redirect_cache", lambda: cache)
    return client, connection, owner, link_id, cache


def test_hit_skips_link_read_but_both_requests_record_clicks(cached_link, monkeypatch):
    client, connection, _, link_id, cache = cached_link
    path = f"/r/{encode_link_id(link_id)}"
    assert client.get(path, follow_redirects=False).status_code == 302
    def unexpected_get(*args, **kwargs):
        pytest.fail("Cache hit must not read the Link row")
    monkeypatch.setattr(Session, "get", unexpected_get)
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/original"
    assert response.headers["cache-control"] == "no-store"
    assert len(connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == link_id)).all()) == 2
    assert cache.client.set.call_count == 1


def test_cached_expiration_returns_404_without_a_click(cached_link):
    client, connection, _, link_id, cache = cached_link
    cache.put(link_id, "https://example.com/", datetime.now(timezone.utc) - timedelta(seconds=1))
    assert client.get(f"/r/{encode_link_id(link_id)}", follow_redirects=False).status_code == 404
    assert connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == link_id)).all() == []


def test_cache_hit_still_redirects_when_click_recording_fails(cached_link, monkeypatch):
    client, _, _, link_id, cache = cached_link
    cache.put(link_id, "https://example.com/", None)
    def fail_commit(*args):
        raise SQLAlchemyError("test failure")
    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.get(f"/r/{encode_link_id(link_id)}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/"


@pytest.mark.parametrize("change,status,destination", [
    ({"destination_url": "https://example.org/new"}, 302, "https://example.org/new"),
    ({"is_active": False}, 404, None),
    ({"expires_at": "2000-01-01T00:00:00Z"}, 404, None),
])
def test_update_invalidates_after_commit(cached_link, change, status, destination):
    client, connection, owner, link_id, cache = cached_link
    path = f"/r/{encode_link_id(link_id)}"
    assert client.get(path, follow_redirects=False).status_code == 302
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        service.update_link(link_id, session, LinkUpdate(**change), owner)
    assert cache.get(link_id) is None
    response = client.get(path, follow_redirects=False)
    assert response.status_code == status
    assert response.headers.get("location") == destination


def test_delete_invalidates(cached_link):
    client, connection, owner, link_id, cache = cached_link
    path = f"/r/{encode_link_id(link_id)}"
    client.get(path, follow_redirects=False)
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        assert service.delete_link(session, link_id, owner)
    assert cache.get(link_id) is None
    assert client.get(path, follow_redirects=False).status_code == 404


def test_unavailable_redis_falls_back_and_mutations_succeed(cached_link):
    client, connection, owner, link_id, cache = cached_link
    for method in (cache.client.get, cache.client.set, cache.client.delete):
        method.side_effect = ConnectionError()
    path = f"/r/{encode_link_id(link_id)}"
    assert client.get(path, follow_redirects=False).status_code == 302
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        assert service.update_link(link_id, session, LinkUpdate(is_active=False), owner)
        assert service.delete_link(session, link_id, owner)
    assert client.get(path, follow_redirects=False).status_code == 404


@pytest.mark.skipif(os.getenv("LINKHUB_TEST_REDIS") != "1", reason="requires local Redis")
def test_real_redis_cache_hit_and_invalidation(cached_link, monkeypatch):
    client, connection, owner, link_id, _ = cached_link
    redis = Redis(host="127.0.0.1", port=6379, socket_timeout=1, socket_connect_timeout=1)
    cache = RedirectCache(redis, prefix=f"linkhub:test:{uuid4().hex}:")
    monkeypatch.setattr(service, "get_redirect_cache", lambda: cache)
    path = f"/r/{encode_link_id(link_id)}"
    try:
        assert client.get(path, follow_redirects=False).status_code == 302
        assert 0 < redis.ttl(f"{cache.prefix}{link_id}") <= 30
        with monkeypatch.context() as patch:
            patch.setattr(Session, "get", lambda *args, **kwargs: pytest.fail("unexpected link read"))
            assert client.get(path, follow_redirects=False).status_code == 302
        assert len(connection.execute(select(ClickEvent.id).where(ClickEvent.link_id == link_id)).all()) == 2
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            service.update_link(link_id, session, LinkUpdate(is_active=False), owner)
        assert cache.get(link_id) is None
        assert client.get(path, follow_redirects=False).status_code == 404
        # Use a short TTL for the same disposable key to verify Redis expiry.
        cache.ttl_seconds = 1
        cache.put(link_id, "https://example.com/", None)
        deadline = time.monotonic() + 3
        while cache.get(link_id) is not None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert cache.get(link_id) is None
    finally:
        redis.delete(f"{cache.prefix}{link_id}")
        redis.close()
