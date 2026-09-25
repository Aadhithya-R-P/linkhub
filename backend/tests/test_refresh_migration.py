"""Exercise data conversion in an isolated, transactionally rolled-back schema."""
from importlib import import_module
import os
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text

from app.db import get_engine

pytestmark = pytest.mark.skipif(
    os.getenv("LINKHUB_TEST_DB") != "1", reason="requires local PostgreSQL"
)


def test_migration_preserves_current_tokens_and_disabled_sessions():
    old = import_module("migrations.versions.2f5adaad97c4_add_refresh_sessions_and_token_history")
    new = import_module("migrations.versions.73dc415cb821_keep_only_current_refresh_token")
    schema = "migration_test_" + uuid4().hex
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(text("CREATE TABLE users (id integer PRIMARY KEY)"))
            connection.execute(text("INSERT INTO users (id) VALUES (1)"))
            with Operations.context(MigrationContext.configure(connection)):
                old.upgrade()
                connection.execute(text("""
                    INSERT INTO refresh_sessions (user_id, expires_at, revoked_at)
                    VALUES
                      (1, now() + interval '7 days', NULL),
                      (1, now() + interval '7 days', now()),
                      (1, now() - interval '1 day', NULL),
                      (1, now() + interval '7 days', NULL),
                      (1, now() + interval '7 days', NULL)
                """))
                connection.execute(text("""
                    INSERT INTO refresh_tokens (session_id, token_hash, used_at)
                    VALUES
                      (1, repeat('a', 64), now()),
                      (1, repeat('b', 64), NULL),
                      (2, repeat('c', 64), NULL),
                      (3, repeat('d', 64), NULL),
                      (4, repeat('e', 64), now())
                """))
                original = connection.execute(text(
                    "SELECT id, expires_at, revoked_at FROM refresh_sessions ORDER BY id"
                )).all()
                new.upgrade()
                rows = connection.execute(text(
                    "SELECT id, token_hash, expires_at, revoked_at FROM refresh_sessions ORDER BY id"
                )).all()
                assert [row.token_hash for row in rows[:3]] == ['b' * 64, 'c' * 64, 'd' * 64]
                assert [(row.id, row.expires_at, row.revoked_at) for row in rows[:3]] == original[:3]
                assert all(row.revoked_at is not None for row in rows[3:])
                assert all(row.token_hash.startswith("unusable-session-") for row in rows[3:])
                assert connection.execute(text("SELECT to_regclass('refresh_tokens')")).scalar_one() is None
                new.downgrade()
                restored = connection.execute(text(
                    "SELECT session_id, token_hash FROM refresh_tokens ORDER BY session_id"
                )).all()
                assert restored == [(row.id, row.token_hash) for row in rows]
        finally:
            transaction.rollback()
