"""Public links for a sent channel post. No network."""
from __future__ import annotations


def channel_message_url(chat_id: int | None, message_id: int | None, username: str | None = None) -> str | None:
    if not chat_id or not message_id:
        return None
    handle = (username or "").strip().lstrip("@")
    if handle and not handle.lstrip("-").isdigit():
        return f"https://t.me/{handle}/{int(message_id)}"
    raw = str(chat_id)
    if raw.startswith("-100"):
        return f"https://t.me/c/{raw[4:]}/{int(message_id)}"
    return None
