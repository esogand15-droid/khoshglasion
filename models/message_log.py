from datetime import datetime, timezone
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class MessageLog(Base):
    __tablename__ = "message_logs"
    __table_args__ = (UniqueConstraint("chat_id", "message_id", name="uq_message_chat_msg"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger, index=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    formatted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    formatted_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_media: Mapped[bool] = mapped_column(Boolean, default=False)
    message_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_used: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    edit_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)
    update_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
