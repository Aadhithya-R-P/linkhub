"""Verify click-event DDL in an isolated schema, rolled back after the test."""
from importlib import import_module
import os
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import inspect, text

from app.db import get_engine


@pytest.mark.skipif(os.getenv("LINKHUB_TEST_DB") != "1", reason="requires local PostgreSQL")
def test_click_migration_upgrade_and_downgrade():
    migration = import_module("migrations.versions.c947e816a230_add_click_events")
    schema = "click_migration_" + uuid4().hex
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(text("CREATE TABLE links (id integer PRIMARY KEY)"))
            connection.execute(text("INSERT INTO links VALUES (1)"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                row = connection.execute(text(
                    "INSERT INTO click_events (link_id) VALUES (1) RETURNING id, clicked_at"
                )).one()
                assert row.id > 0 and row.clicked_at.tzinfo is not None
                indexes = inspect(connection).get_indexes("click_events", schema=schema)
                assert any(index["column_names"] == ["link_id", "clicked_at"] for index in indexes)
                connection.execute(text("DELETE FROM links WHERE id = 1"))
                assert connection.execute(text("SELECT count(*) FROM click_events")).scalar_one() == 0
                migration.downgrade()
                assert not inspect(connection).has_table("click_events", schema=schema)
                assert inspect(connection).has_table("links", schema=schema)
        finally:
            transaction.rollback()
