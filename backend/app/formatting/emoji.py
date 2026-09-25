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


_SKIN = range(0x1F3FB, 0x1F400)
_REGIONAL = range(0x1F1E6, 0x1F200)
_EXTRA_EMOJI = {
    0xA9, 0xAE, 0x203C, 0x2049, 0x2122, 0x2139,
    0x2194, 0x2195, 0x2196, 0x2197, 0x2198, 0x2199,
    0x21A9, 0x21AA,
    0x231A, 0x231B, 0x2328, 0x23CF,
    0x23E9, 0x23EA, 0x23EB, 0x23EC, 0x23ED, 0x23EE, 0x23EF,
    0x23F0, 0x23F1, 0x23F2, 0x23F3, 0x23F8, 0x23F9, 0x23FA,
    0x24C2, 0x25AA, 0x25AB, 0x25B6, 0x25C0,
    0x25FB, 0x25FC, 0x25FD, 0x25FE,
    0x2934, 0x2935, 0x2B05, 0x2B06, 0x2B07,
    0x2B1B, 0x2B1C, 0x2B50, 0x2B55,
    0x3030, 0x303D, 0x3297, 0x3299,
}


def _is_emoji_base(ch: str) -> bool:
    code = ord(ch)
    if code in _REGIONAL or code in _EXTRA_EMOJI:
        return True
    return (
        0x1F000 <= code <= 0x1F0FF
        or 0x1F300 <= code <= 0x1FAFF
        or 0x2600 <= code <= 0x26FF
        or 0x2700 <= code <= 0x27BF
    )


def _consume_emoji_modifiers(text: str, index: int) -> int:
    if index < len(text) and text[index] == "\ufe0f":
        index += 1
    if index < len(text) and ord(text[index]) in _SKIN:
        index += 1
        if index < len(text) and text[index] == "\ufe0f":
            index += 1
    return index


def _emoji_end(text: str, index: int) -> int | None:
    """End offset of one emoji grapheme, not a run of them."""
    if index >= len(text):
        return None
    ch = text[index]
    code = ord(ch)
    if code in _REGIONAL:
        if index + 1 < len(text) and ord(text[index + 1]) in _REGIONAL:
            return index + 2
        return None
    if ch in "#*0123456789":
        cursor = index + 1
        if cursor < len(text) and text[cursor] == "\ufe0f":
            cursor += 1
        if cursor < len(text) and text[cursor] == "\u20e3":
            return cursor + 1
        return None
    if not _is_emoji_base(ch):
        return None
    cursor = _consume_emoji_modifiers(text, index + 1)
    while cursor < len(text) and text[cursor] == "\u200d":
        nxt = cursor + 1
        if nxt >= len(text) or not _is_emoji_base(text[nxt]):
            break
        cursor = _consume_emoji_modifiers(text, nxt + 1)
    return cursor


def emoji_graphemes(text: str) -> list[tuple[int, int, str]]:
    """Split emoji into separate clusters. A gold row must not be one cluster."""
    spans: list[tuple[int, int, str]] = []
    index = 0
    while index < len(text or ""):
        end = _emoji_end(text, index)
        if end is None:
            index += 1
            continue
        spans.append((index, end, text[index:end]))
        index = end
    return spans


def first_emoji_grapheme(text: str) -> str | None:
    spans = emoji_graphemes(text or "")
    return spans[0][2] if spans else None


def custom_emoji_span_valid(text: str, start: int, length: int) -> bool:
    """A custom emoji entity must cover exactly one emoji, never a whole row."""
    if length <= 0 or start < 0 or start + length > len(text or ""):
        return False
    snippet = text[start:start + length]
    spans = emoji_graphemes(snippet)
    return len(spans) == 1 and spans[0][0] == 0 and spans[0][1] == len(snippet)


def should_replace(category: str, mapping: EmojiMapping) -> bool:
    if not mapping.enabled or not mapping.custom_emoji_id or not mapping.unicode_emoji:
        return False
    if not str(mapping.custom_emoji_id).isdigit():
        return False
    from backend.app.formatting.spectrum import spectrum_of

    wanted = spectrum_of(category)
    mapped = (mapping.category or "").strip()
    if mapped in {"divider", "membership", "support"}:
        return True
    if mapped:
        return spectrum_of(mapped) == wanted
    # An unclassified glyph must not be sprayed onto every post that happens
    # to contain the same unicode character.
    return False


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
