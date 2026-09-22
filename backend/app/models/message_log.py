from sqlalchemy import String, Integer, DateTime, Text, Float
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from backend.app.db.base import Base
import uuid

def utcnow():
    return datetime.now(timezone.utc)

class MessageLog(Base):
    __tablename__ = "message_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[int] = mapped_column(Integer, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    formatted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    formatted_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # edited, skipped, failed, dry_run
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_media: Mapped[bool] = mapped_column(default=False)
    message_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
