from concurrent.futures import ThreadPoolExecutor
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import ConnectionError, TimeoutError
from redis.retry import Retry

from app import rate_limit
from app.config import Settings
from app.db import get_db
from app.dependencies import get_current_user
from app.main import app
from app.routes import links as link_routes


@pytest.fixture
def limiter(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    fake = Mock()
    fake.check.return_value = 0
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: fake)
    return fake


@pytest.mark.parametrize("ttl,seconds", [(1, 1), (1000, 1), (1001, 2), (59999, 60)])
def test_retry_after_rounds_up_and_keys_hide_identity(ttl, seconds):
    redis = Mock()
    redis.eval.return_value = [0, ttl]
    limiter = rate_limit.RateLimiter(redis, "test-secret")
    assert limiter.check("mutation", "user:12345", 60, 60) == seconds
    key = redis.eval.call_args.args[2]
    assert key.startswith("linkhub:limit:v1:mutation:60:60:")
    assert "user:12345" not in key


def test_disabled_limit_does_not_connect(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: pytest.fail("must not connect"))
    rate_limit.enforce_mutation_limit(1, Settings(rate_limit_enabled=False))


@pytest.mark.parametrize("failure", [ConnectionError, TimeoutError])
def test_outage_allows_mutations_without_logging_details(limiter, caplog, failure):
    limiter.check.side_effect = failure("secret-redis-url")
    rate_limit.enforce_mutation_limit(1, Settings())
    assert "allowing the request" in caplog.text
    assert "secret-redis-url" not in caplog.text


def test_blocked_request_has_retry_and_no_store(limiter):
    limiter.check.return_value = 12
    with pytest.raises(HTTPException) as exc:
        rate_limit.enforce_mutation_limit(7, Settings())
    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "12", "Cache-Control": "no-store"}
    limiter.check.assert_called_once_with("mutation", "user:7", 60, 60)


def test_all_mutations_use_same_authenticated_identity_and_ignore_ip_headers(limiter, monkeypatch):
    limiter.check.return_value = 8
    user = SimpleNamespace(id=7)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(link_routes, "create_link", lambda *a: pytest.fail("blocked create ran"))
    monkeypatch.setattr(link_routes, "update_link", lambda *a: pytest.fail("blocked update ran"))
    monkeypatch.setattr(link_routes, "delete_link", lambda *a: pytest.fail("blocked delete ran"))
    try:
        with TestClient(app) as client:
            for method, path, body in [
                ("POST", "/api/links", {"destination_url": "https://example.com"}),
                ("PATCH", "/api/links/1", {"is_active": False}),
                ("DELETE", "/api/links/1", None),
            ]:
                response = client.request(method, path, json=body,
                    headers={"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"})
                assert response.status_code == 429
                assert response.headers["retry-after"] == "8"
                assert response.headers["cache-control"] == "no-store"
            assert all(call.args[:2] == ("mutation", "user:7") for call in limiter.check.call_args_list)
            user.id = 8
            client.delete("/api/links/1")
            assert limiter.check.call_args.args[1] == "user:8"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


def test_unauthenticated_mutation_does_not_consume_budget(limiter):
    app.dependency_overrides[get_db] = lambda: None
    try:
        with TestClient(app) as client:
            assert client.post("/api/links", json={"destination_url": "https://example.com"}).status_code == 401
        limiter.check.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_reads_logout_and_public_redirects_do_not_call_limiter(limiter, monkeypatch):
    from app.routes import auth, redirects
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
    monkeypatch.setattr(link_routes, "list_links", lambda *a: ([], None))
    monkeypatch.setattr(auth, "revoke_refresh_session", lambda *a: None)
    monkeypatch.setattr(redirects, "get_redirect_destination", lambda *a: None)
    try:
        with TestClient(app) as client:
            assert client.get("/api/links").status_code == 200
            assert client.post("/api/auth/logout").status_code == 204
            assert client.get("/r/1").status_code == 404
        limiter.check.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.skipif(os.getenv("LINKHUB_TEST_REDIS") != "1", reason="requires local Redis")
def test_real_redis_atomic_shared_limit_expiry_and_separate_users():
    client = Redis(host="127.0.0.1", port=6379, socket_timeout=2, socket_connect_timeout=2,
                   retry=Retry(NoBackoff(), 0))
    # Fail promptly when the opt-in service is unavailable, before starting workers.
    try:
        client.ping()
    except Exception:
        client.close()
        raise
    prefix = f"linkhub:test:limit:{uuid4().hex}:"
    first = rate_limit.RateLimiter(client, "test-secret", prefix)
    second = rate_limit.RateLimiter(client, "test-secret", prefix)
    try:
        # Two limiter objects represent workers sharing Redis, with concurrent requests.
        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(lambda i: (first if i % 2 else second).check("mutation", "user:1", 5, 30), range(24)))
        assert outcomes.count(0) == 5
        assert all(1 <= result <= 30 for result in outcomes if result)
        assert first.check("mutation", "user:2", 5, 30) == 0
        assert first.check("expiry", "user:1", 1, 1) == 0
        assert second.check("expiry", "user:1", 1, 1) == 1
        # Poll only TTL, not the limiter, so the test cannot start the next window early.
        key = next(client.scan_iter(match=prefix + "expiry:*"))
        deadline = time.monotonic() + 3
        while client.exists(key) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not client.exists(key)
        assert second.check("expiry", "user:1", 1, 1) == 0
    finally:
        for key in client.scan_iter(match=prefix + "*"):
            client.delete(key)
        client.close()
