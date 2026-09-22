from sqlalchemy import String, Boolean, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from backend.app.db.base import Base
import uuid

def utcnow():
    return datetime.now(timezone.utc)

class EmojiMapping(Base):
    __tablename__ = "emoji_mappings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    unicode_emoji: Mapped[str] = mapped_column(String(32))
    custom_emoji_id: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contexts: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array string
    priority: Mapped[int] = mapped_column(Integer, default=50)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
