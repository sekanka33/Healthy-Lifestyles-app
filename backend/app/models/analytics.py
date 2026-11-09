import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserActivityDay(Base):
    """One row per user per UTC day on which they used the app (any authenticated request).
    Source for daily/monthly active users; holds no content, only the fact of activity."""

    __tablename__ = "user_activity_days"
    __table_args__ = (Index("ix_user_activity_days_day", "day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
