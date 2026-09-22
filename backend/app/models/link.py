from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Identity, Index, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (Index("ix_links_user_id_id", "user_id", "id"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    destination_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(server_default=true())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
