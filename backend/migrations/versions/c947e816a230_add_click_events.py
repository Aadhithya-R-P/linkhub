"""Add click events for successful redirect requests.

Revision ID: c947e816a230
Revises: 73dc415cb821
"""
from alembic import op
import sqlalchemy as sa

revision = "c947e816a230"
down_revision = "73dc415cb821"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "click_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("link_id", sa.Integer(), sa.ForeignKey("links.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clicked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_click_events_link_id_clicked_at", "click_events", ["link_id", "clicked_at"])


def downgrade() -> None:
    op.drop_index("ix_click_events_link_id_clicked_at", table_name="click_events")
    op.drop_table("click_events")
