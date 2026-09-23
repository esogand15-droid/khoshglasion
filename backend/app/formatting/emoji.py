from __future__ import annotations

from dataclasses import dataclass
import html
import re

from backend.app.formatting.textutil import URL_RE

@dataclass
class EmojiMapping:
    unicode_emoji: str
    custom_emoji_id: str
    enabled: bool = True
    contexts: list | None = None
    priority: int = 50
    category: str | None = None


def should_replace(category: str, mapping: EmojiMapping) -> bool:
    if not mapping.enabled or not mapping.custom_emoji_id or not mapping.unicode_emoji:
        return False
    if not str(mapping.custom_emoji_id).isdigit():
        return False
    if not mapping.contexts:
        return True
    return category in mapping.contexts


def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(not (end <= a or start >= b) for a, b in occupied)


def _inside_url(text: str, pos: int) -> bool:
    for match in URL_RE.finditer(text):
        if match.start() <= pos < match.end():
            return True
    return False


def find_emoji_spans(
    text: str,
    mappings: list[EmojiMapping],
    category: str,
    max_emoji: int = 12,
    force: bool = False,
    avoid_ids: set[str] | None = None,
) -> list[tuple[int, int, str, str]]:
    """Return non-overlapping (start, end, emoji, custom_id) spans.

    Recently used custom ids are tried last, so the same glyph can rotate
    without dropping the replacement when it is the only candidate.
    """
    if not text or not mappings or max_emoji <= 0:
        return []
    occupied: list[tuple[int, int]] = []
    spans: list[tuple[int, int, str, str]] = []
    avoided = {str(item) for item in (avoid_ids or set())}
    ordered = sorted(
        mappings,
        key=lambda m: (1 if str(m.custom_emoji_id) in avoided else 0, -m.priority, -len(m.unicode_emoji or "")),
    )
    for mapping in ordered:
        if not should_replace(category, mapping):
            if not force:
                continue
            if not mapping.enabled or not str(mapping.custom_emoji_id).isdigit():
                continue
        emoji = mapping.unicode_emoji
        cursor = 0
        while cursor < len(text):
            pos = text.find(emoji, cursor)
            if pos < 0:
                break
            end = pos + len(emoji)
            cursor = end
            if _overlaps(pos, end, occupied) or _inside_url(text, pos):
                continue
            spans.append((pos, end, emoji, str(mapping.custom_emoji_id)))
            occupied.append((pos, end))
            if len(spans) >= max_emoji:
                return sorted(spans)
    return sorted(spans)


def render_emoji_html(text: str, spans: list[tuple[int, int, str, str]]) -> str:
    """Escape the whole message, then wrap only the mapped emoji spans."""
    if not spans:
        return html.escape(text)
    parts: list[str] = []
    last = 0
    for start, end, emoji, custom_id in spans:
        parts.append(html.escape(text[last:start]))
        parts.append(f'<tg-emoji emoji-id="{html.escape(custom_id, quote=True)}">{html.escape(emoji)}</tg-emoji>')
        last = end
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def build_emoji_entities(
    text: str,
    mappings: list[EmojiMapping],
    category: str,
    max_emoji: int = 12,
) -> tuple[str, list[dict]]:
    spans = find_emoji_spans(text, mappings, category, max_emoji=max_emoji, force=False)
    if not spans:
        spans = find_emoji_spans(text, mappings, category, max_emoji=max_emoji, force=True)
    html_text = render_emoji_html(text, spans)
    entities = [
        {"type": "custom_emoji", "offset": start, "length": end - start, "custom_emoji_id": cid}
        for start, end, _emoji, cid in spans
    ]
    return html_text, entities


_TAG_RE = re.compile(r"<[^>]+>")


def visible_length(text: str, html_text: str | None = None) -> int:
    if html_text:
        return len(_TAG_RE.sub("", html_text))
    return len(text or "")
