from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.system import utcnow
import uuid


class TelegramAccount(Base):
    """One logged-in Telegram user. The session string never leaves the server."""

    __tablename__ = "telegram_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_masked: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    premium: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    roles: Mapped[str] = mapped_column(String(32), default="emoji,news")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    join_public: Mapped[bool] = mapped_column(Boolean, default=False)
    api_id: Mapped[str] = mapped_column(String(16), default="")
    api_hash: Mapped[str] = mapped_column(Text, default="")
    session_string: Mapped[str] = mapped_column(Text, default="")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
