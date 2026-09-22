from sqlalchemy import String, Boolean, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from backend.app.db.base import Base
import uuid

def utcnow():
    return datetime.now(timezone.utc)

class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_beautify: Mapped[bool] = mapped_column(Boolean, default=True)
    emoji_replacement: Mapped[bool] = mapped_column(Boolean, default=True)
    style_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    header_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    processing_mode: Mapped[str] = mapped_column(String(32), default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
