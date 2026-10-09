from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClickEvent(Base):
    __tablename__ = "click_events"
    __table_args__ = (Index("ix_click_events_link_id_clicked_at", "link_id", "clicked_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id", ondelete="CASCADE"))
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
