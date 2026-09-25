"""Keep a Telegram caption and its emoji entities on the same slice.

A custom-emoji entity past the cut is dropped, not shifted onto the wrong
letters. Stripping those spans is not a unicode substitute: the glyph goes
away with the entity so a failed premium send can still deliver the photo.
"""
from __future__ import annotations


def clip_text_entities(
    text: str,
    entities: list[dict] | None,
    limit: int,
) -> tuple[str, list[dict] | None]:
    body = text or ""
    if limit <= 0:
        return "", None
    if len(body) > limit:
        cut = body.rfind("\n", 0, limit)
        body = body[: cut if cut >= limit // 2 else limit].rstrip()
    kept: list[dict] = []
    for item in entities or []:
        start = int(item.get("offset") or 0)
        length = int(item.get("length") or 0)
        if length <= 0 or start < 0 or start + length > len(body):
            continue
        kept.append(item)
    return body, kept or None


def strip_custom_emoji_spans(text: str, entities: list[dict] | None) -> str:
    spans = []
    for item in entities or []:
        if item.get("type") != "custom_emoji":
            continue
        start = int(item.get("offset") or 0)
        length = int(item.get("length") or 0)
        if length > 0 and start >= 0:
            spans.append((start, start + length))
    if not spans:
        return (text or "").strip()
    parts: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        if start < cursor:
            continue
        parts.append((text or "")[cursor:start])
        cursor = end
    parts.append((text or "")[cursor:])
    return "".join(parts).strip()
