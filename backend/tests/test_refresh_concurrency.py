"""Real concurrent transactions: temporarily commit fixture rows, then delete them.

The ordinary savepoint fixture cannot test locks across independent connections.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from queue import Queue
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_engine
from app.models import RefreshSession, User
from app.security import hash_refresh_token
from app.services.refresh import (
    InvalidRefreshToken, revoke_refresh_session, rotate_refresh_token, start_refresh_session,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LINKHUB_TEST_DB") != "1", reason="requires migrated local PostgreSQL"
)


@pytest.fixture
def committed_login():
    user_id = None
    try:
        with Session(get_engine()) as session:
            user = User(email=f"{uuid4().hex}@example.test", password_hash="test-only")
            session.add(user)
            session.flush()
            user_id = user.id
            raw_token, _ = start_refresh_session(session, user_id, Settings())
        yield user_id, raw_token
    finally:
        if user_id is not None:
            with get_engine().begin() as connection:
                connection.execute(delete(RefreshSession).where(RefreshSession.user_id == user_id))
                connection.execute(delete(User).where(User.id == user_id))


@pytest.mark.parametrize("first_action", ["refresh", "logout"])
def test_waiting_refresh_observes_committed_state(committed_login, first_action):
    user_id, raw_token = committed_login
    worker_pid = Queue()

    def competing_refresh():
        with Session(get_engine()) as session:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            worker_pid.put(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
            try:
                rotate_refresh_token(session, raw_token)
            except InvalidRefreshToken:
                return "rejected"
            return "accepted"

    with ThreadPoolExecutor(max_workers=1) as executor:
        with Session(get_engine()) as holder:
            holder.execute(select(RefreshSession).where(
                RefreshSession.user_id == user_id,
            ).with_for_update()).scalar_one()
            future = executor.submit(competing_refresh)
            try:
                pid = worker_pid.get(timeout=5)
                deadline = monotonic() + 5
                with get_engine().connect() as observer:
                    while True:
                        blockers = observer.execute(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": pid},
                        ).scalar_one()
                        if blockers:
                            break
                        assert monotonic() < deadline, "Competing refresh never waited for the session lock"
                        sleep(0.01)
                if first_action == "refresh":
                    _, successor, _ = rotate_refresh_token(holder, raw_token)
                else:
                    revoke_refresh_session(holder, raw_token)
            finally:
                holder.rollback()  # Also release the lock if an assertion fails.
        assert future.result(timeout=10) == "rejected"

    with Session(get_engine()) as session:
        login_session = session.execute(select(RefreshSession).where(
            RefreshSession.user_id == user_id,
        )).scalar_one()
        if first_action == "refresh":
            assert login_session.revoked_at is None
            assert login_session.token_hash == hash_refresh_token(successor)
            # The loser must not invalidate the winner's replacement.
            assert rotate_refresh_token(session, successor)[0] == user_id
        else:
            assert login_session.revoked_at is not None
            with pytest.raises(InvalidRefreshToken):
                rotate_refresh_token(session, raw_token)
