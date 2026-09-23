from __future__ import annotations

from dataclasses import dataclass, field
import re

from backend.app.formatting.category import detect_category
from backend.app.formatting.emoji import EmojiMapping as EmojiMap
from backend.app.formatting.richtext import prepare_post
from backend.app.formatting.rotation import apply_structure
from backend.app.formatting.styles import StyleConfig, get_style, style_for_category
from backend.app.formatting.textutil import normalize_persian
from backend.app.formatting.validators import validate_length

CATEGORY_LEAD_EMOJI: dict[str, str] = {
    "announcement": "🚨",
    "news": "📢",
    "resource": "📚",
    "book": "📚",
    "exam": "📝",
    "planning": "🎯",
    "motivational": "⭐",
    "consulting": "💡",
    "schedule": "📅",
    "rank": "🏆",
    "discount": "🎁",
    "ad": "🎉",
    "qa": "❓",
    "registration": "📌",
    "school": "🏫",
    "major_choice": "🎓",
    "general": "✨",
}


@dataclass
class FormattedMessage:
    text: str
    is_caption: bool
    category: str
    style_slug: str
    changed: bool
    applied_rules: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    html_text: str | None = None
    entities: list | None = None
    emoji_spans: list[tuple[int, int, str]] = field(default_factory=list)


def _normalize_spacing(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _normalize_bullets(text: str) -> tuple[str, bool]:
    changed = False
    new_text, count = re.subn(r"(?m)^\s*[•▪·]\s*", "🔹 ", text)
    if count:
        changed = True
        text = new_text
    new_text, count = re.subn(r"(?m)^\s*[-–—]\s+(?=\S)", "🔹 ", text)
    if count:
        changed = True
        text = new_text
    new_text, count = re.subn(r"(?m)^\s*🔶\s*", "🔶 ", text)
    if count:
        changed = True
        text = new_text
    return text, changed


def _trim_to_limit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    clipped = text[: max(0, limit - 1)].rstrip()
    # Prefer cutting on a line boundary so a caption does not end mid-word.
    newline = clipped.rfind("\n")
    if newline > int(limit * 0.6):
        clipped = clipped[:newline].rstrip()
    return clipped + "…"


def format_message(
    raw_text: str,
    is_caption: bool = False,
    channel_style_slug: str | None = None,
    footer_text: str | None = None,
    emoji_mappings: list[EmojiMap] | None = None,
    header_enabled: bool = True,
    enable_emoji: bool = True,
    enable_spacing: bool = True,
    persian_normalize: bool = False,
    max_emoji: int = 12,
    style_config: StyleConfig | None = None,
    entities: list | None = None,
    footer_url: str | None = None,
    support_username: str | None = None,
    category: str | None = None,
    structure_id: str | None = None,
    body_emoji: bool = True,
    avoid_emoji_ids: set[str] | None = None,
) -> FormattedMessage:
    original = raw_text or ""
    text = original
    applied: list[str] = []
    warnings: list[str] = []

    category = category or detect_category(text)
    style_slug = channel_style_slug or style_for_category(category)
    style = style_config or get_style(style_slug)

    if persian_normalize:
        new_text = normalize_persian(text)
        if new_text != text:
            applied.append("persian_normalize")
            text = new_text

    if enable_spacing:
        new_text = _normalize_spacing(text)
        if new_text != text:
            applied.append("normalize_spacing")
            text = new_text

    new_text, bullet_changed = _normalize_bullets(text)
    if bullet_changed:
        applied.append("normalize_bullets")
        text = new_text

    incoming = entities
    preserve_offsets = bool(incoming) and "\r" not in original
    if preserve_offsets:
        text = original
    else:
        structured = apply_structure(text, structure_id)
        if structured != text:
            applied.append(f"structure:{structure_id}")
            text = structured
        if header_enabled and style.header_template and style.header_template not in text[:80]:
            text = f"{style.header_template}\n\n{text.lstrip()}"
            applied.append("add_header")

    footer = (footer_text if footer_text is not None else style.footer_template) or ""
    limit = 1024 if is_caption else 4096
    room_for_chrome = len(text) <= max(0, limit - 80)
    prepared, html_text, entity_dicts, emoji_spans, chrome_rules = prepare_post(
        text,
        raw_entities=incoming if preserve_offsets else None,
        add_footer=bool(style.add_footer and footer and room_for_chrome),
        add_divider=bool(style.use_divider_bottom and style.divider and room_for_chrome),
        footer_text=footer,
        footer_url=footer_url,
        support_username=support_username,
        mappings=emoji_mappings,
        category=category,
        max_emoji=max_emoji,
        enable_emoji=enable_emoji,
        body_emoji=body_emoji,
        avoid_emoji_ids=avoid_emoji_ids,
    )
    text = prepared
    applied.extend(rule for rule in chrome_rules if rule not in applied)
    if len(text) > limit:
        text = _trim_to_limit(text, limit)
        warnings.append(f"trimmed to {limit} characters")
        applied.append("trim_to_limit")
        html_text = None
        entity_dicts = None
        emoji_spans = []

    ok, err = validate_length(text, is_caption)
    if not ok:
        warnings.append(err or "invalid length")
        return FormattedMessage(
            text=original,
            is_caption=is_caption,
            category=category,
            style_slug=style.slug,
            changed=False,
            applied_rules=[],
            warnings=warnings,
        )

    changed = text != original or bool(html_text and any(token in html_text for token in ("<tg-emoji", "<blockquote", "<a ")))
    return FormattedMessage(
        text=text,
        is_caption=is_caption,
        category=category,
        style_slug=style.slug,
        changed=changed,
        applied_rules=applied,
        warnings=warnings,
        html_text=html_text,
        entities=entity_dicts,
        emoji_spans=emoji_spans,
    )
