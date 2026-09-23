from __future__ import annotations

from dataclasses import dataclass, field
import re

from backend.app.formatting.category import detect_category
from backend.app.formatting.emoji import EmojiMapping as EmojiMap
from backend.app.formatting.emoji import find_emoji_spans, render_emoji_html
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
) -> FormattedMessage:
    original = raw_text or ""
    text = original
    applied: list[str] = []
    warnings: list[str] = []

    category = detect_category(text)
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

    if header_enabled and style.header_template and style.header_template not in text[:80]:
        text = f"{style.header_template}\n\n{text.lstrip()}"
        applied.append("add_header")

    footer = (footer_text if footer_text is not None else style.footer_template) or ""
    divider = style.divider or ""
    if footer and divider and footer.strip().startswith(divider.strip()):
        footer = footer.strip()[len(divider.strip()):].strip()

    body_without_chrome = text
    if style.add_footer and footer and footer.strip() not in text:
        if style.use_divider_bottom and divider and divider not in text.split("\n")[-6:]:
            text = text.rstrip() + "\n\n" + divider + "\n\n" + footer.strip()
            applied.append("add_footer_with_divider")
        else:
            text = text.rstrip() + "\n\n" + footer.strip()
            applied.append("add_footer")
    elif footer and footer.strip() in text:
        warnings.append("footer already present, skipped")

    if enable_emoji and header_enabled and category in CATEGORY_LEAD_EMOJI:
        has_mapped = any(m.unicode_emoji and m.unicode_emoji in text for m in (emoji_mappings or []))
        has_generic = any(
            (0x2600 <= ord(ch) <= 0x27BF) or (0x1F300 <= ord(ch) <= 0x1FAFF)
            for ch in text
        )
        if not has_mapped and not has_generic:
            lead = CATEGORY_LEAD_EMOJI.get(category, "✨")
            text = f"{lead} {text}"
            applied.append(f"auto_emoji:{lead}")

    limit = 1024 if is_caption else 4096
    if len(text) > limit:
        # Drop chrome first. Never silently destroy the admin's wording if the
        # body itself already exceeds Telegram's limit.
        if len(body_without_chrome) <= limit < len(text):
            text = body_without_chrome
            warnings.append("footer dropped to fit telegram limit")
            applied.append("drop_footer_for_limit")
        else:
            text = _trim_to_limit(body_without_chrome, limit)
            warnings.append(f"trimmed to {limit} characters")
            applied.append("trim_to_limit")

    html_text = None
    entities = None
    emoji_spans: list[tuple[int, int, str]] = []
    if enable_emoji and emoji_mappings:
        spans = find_emoji_spans(text, emoji_mappings, category, max_emoji=max_emoji, force=False)
        if not spans:
            spans = find_emoji_spans(text, emoji_mappings, category, max_emoji=max_emoji, force=True)
        if spans:
            html_text = render_emoji_html(text, spans)
            entities = [
                {"type": "custom_emoji", "offset": start, "length": end - start, "custom_emoji_id": cid}
                for start, end, _emoji, cid in spans
            ]
            emoji_spans = [(start, end, cid) for start, end, _emoji, cid in spans]
            applied.append(f"emoji_replacement:{len(spans)}")

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

    changed = text != original or bool(html_text and "<tg-emoji" in html_text)
    return FormattedMessage(
        text=text,
        is_caption=is_caption,
        category=category,
        style_slug=style.slug,
        changed=changed,
        applied_rules=applied,
        warnings=warnings,
        html_text=html_text,
        entities=entities,
        emoji_spans=emoji_spans,
    )
