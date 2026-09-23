"""Preserve Telegram entities while extracting text."""
from dataclasses import dataclass
import re

@dataclass
class RawMessage:
    text: str | None
    caption: str | None
    entities: list | None
    caption_entities: list | None
    chat_id: int
    message_id: int
    has_media: bool
    media_type: str | None

    @property
    def effective_text(self) -> str | None:
        return self.caption if self.has_media else self.text

    @property
    def effective_entities(self):
        return self.caption_entities if self.has_media else self.entities

@dataclass
class ParsedSegment:
    text: str
    type: str  # plain, url, mention, hashtag, bold, etc.

URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@[A-Za-z0-9_]+")
HASHTAG_RE = re.compile(r"#[\w\u0600-\u06FF]+")

def extract_text(raw: RawMessage) -> str | None:
    return raw.effective_text

def has_editable_content(raw: RawMessage) -> bool:
    t = raw.effective_text
    return bool(t and t.strip())

def detect_media_type(msg: dict) -> str | None:
    for k in ["photo","video","animation","document","audio","voice","sticker","poll","location","contact"]:
        if k in msg:
            return k
    return None
