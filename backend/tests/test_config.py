import pytest
from pydantic import ValidationError

from app.config import Settings


def production(**overrides):
    values = dict(environment="production", db_host="db.example.com", db_port=5432,
                  db_name="example", db_user="example", db_password="test-only",
                  jwt_secret="x" * 32, refresh_cookie_secure=True,
                  auth_allowed_origins=["https://example.vercel.app"],
                  db_sslmode="verify-full", db_sslrootcert="system",
                  redis_url="rediss://localhost:6379/0")
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_tls_options_reach_shared_database_url():
    assert dict(production().get_database_url().query) == {
        "sslmode": "verify-full", "sslrootcert": "system"}


@pytest.mark.parametrize("overrides", [
    {"refresh_cookie_secure": False},
    {"auth_allowed_origins": []},
    {"auth_allowed_origins": ["https://*.vercel.app"]},
    {"auth_allowed_origins": ["http://example.com"]},
    {"auth_allowed_origins": ["https://example.com/path"]},
    {"db_sslmode": "prefer"},
    {"db_sslrootcert": None},
    {"redis_url": "redis://localhost:6379/0"},
])
def test_rejects_unsafe_production_settings(overrides):
    with pytest.raises(ValidationError):
        production(**overrides)
