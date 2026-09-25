"""Keep only the current refresh token on each login row.

Revision ID: 73dc415cb821
Revises: 2f5adaad97c4

Downgrade restores the old schema with one token per session; discarded token
history cannot be recovered.
"""
from alembic import op
import sqlalchemy as sa

revision = "73dc415cb821"
down_revision = "2f5adaad97c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("refresh_sessions", sa.Column("token_hash", sa.String(64), nullable=True))
    # Choose the current unused token. Preserve revoked/expired session state.
    op.execute("""
        UPDATE refresh_sessions AS s
        SET token_hash = (
            SELECT t.token_hash FROM refresh_tokens AS t
            WHERE t.session_id = s.id AND t.used_at IS NULL
            ORDER BY t.id DESC LIMIT 1
        )
    """)
    # Incomplete sessions must not become usable. The marker cannot match a
    # SHA-256 hex digest and remains unique without retaining any token history.
    op.execute("""
        UPDATE refresh_sessions
        SET token_hash = 'unusable-session-' || id::text,
            revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP)
        WHERE token_hash IS NULL
    """)
    op.alter_column("refresh_sessions", "token_hash", nullable=False)
    op.create_unique_constraint("refresh_sessions_token_hash_key", "refresh_sessions", ["token_hash"])
    op.drop_table("refresh_tokens")


def downgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), sa.Identity(always=True), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("refresh_sessions.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"])
    op.execute("""
        INSERT INTO refresh_tokens (session_id, token_hash)
        SELECT id, token_hash FROM refresh_sessions
    """)
    op.drop_constraint("refresh_sessions_token_hash_key", "refresh_sessions", type_="unique")
    op.drop_column("refresh_sessions", "token_hash")
