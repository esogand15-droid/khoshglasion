from datetime import datetime, timezone
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_beautify: Mapped[bool] = mapped_column(Boolean, default=True)
    emoji_replacement: Mapped[bool] = mapped_column(Boolean, default=True)
    style_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    header_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_mode: Mapped[str] = mapped_column(String(32), default="auto")
    ai_rewrite: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    edit_delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signature_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    skip_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_chars: Mapped[int] = mapped_column(Integer, default=1)
    preserve_buttons: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    posts_edited: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
