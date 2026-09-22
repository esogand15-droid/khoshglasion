import hashlib
import re
import html
from dataclasses import dataclass, field

from backend.app.formatting.category import detect_category
from backend.app.formatting.styles import get_style, style_for_category, DIVIDER
from backend.app.formatting.validators import validate_length
from backend.app.formatting.emoji import build_emoji_entities, EmojiMapping as EmojiMap

BULLET_VARIANTS = ["🔶", "•", "▪", "·", "-"]

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

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def _normalize_spacing(text: str) -> str:
    # collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # trim trailing spaces per line
    lines = [l.rstrip() for l in text.split("\n")]
    # remove leading/trailing empty
    text = "\n".join(lines).strip()
    return text

def _normalize_bullets(text: str) -> tuple[str, bool]:
    """Convert • / 🔶 bullets to 🔹 style for consistency."""
    changed = False
    # Replace "• " at line start with "🔹 "
    new_text, n1 = re.subn(r"(?m)^\s*•\s*", "🔹 ", text)
    if n1:
        changed = True
        text = new_text
    # Keep 🔶 but normalize spacing
    new_text, n2 = re.subn(r"(?m)^\s*🔶\s*", "🔶 ", text)
    if n2:
        changed = True
        text = new_text
    # If bullet lines exist but inconsistent, unify to 🔹
    # Detect if text has bullets with •
    return text, changed

def _smart_paragraphs(text: str) -> str:
    # Ensure double newline between paragraphs is consistent
    # Don't break bullet lists
    lines = text.split("\n")
    out = []
    for line in lines:
        out.append(line)
    return "\n".join(out)

def format_message(
    raw_text: str,
    is_caption: bool = False,
    channel_style_slug: str | None = None,
    footer_text: str | None = None,
    emoji_mappings: list[EmojiMap] | None = None,
    header_enabled: bool = True,
    enable_emoji: bool = True,
    enable_spacing: bool = True,
) -> FormattedMessage:
    original = raw_text
    text = raw_text
    applied: list[str] = []
    warnings: list[str] = []

    category = detect_category(text)
    style_slug = channel_style_slug or style_for_category(category)
    style = get_style(style_slug)

    # 1. Normalize spacing
    if enable_spacing:
        new_text = _normalize_spacing(text)
        if new_text != text:
            applied.append("normalize_spacing")
            text = new_text

    # 2. Normalize bullets
    new_text, bullet_changed = _normalize_bullets(text)
    if bullet_changed:
        applied.append("normalize_bullets")
        text = new_text

    # 3. Smart paragraphs
    text = _smart_paragraphs(text)

    # --- Do NOT rewrite semantic content ---
    # Only beautification: dividers, footer, emoji enhancement

    # 4. Add divider + footer if style says so
    # Check if footer already exists to avoid duplication
    footer = footer_text or style.footer_template
    if style.add_footer and footer:
        # Avoid double footer
        if footer.strip() not in text:
            # Add divider before footer if needed
            if style.divider and style.divider not in text.split("\n")[-5:]:
                text = text.rstrip() + "\n\n" + style.divider + "\n\n" + footer
                applied.append("add_footer_with_divider")
            else:
                text = text.rstrip() + "\n\n" + footer
                applied.append("add_footer")
        else:
            warnings.append("footer already present, skipped")

    # 5. Emoji custom mapping (HTML mode)
    html_text = None
    entities_extra = None
    if enable_emoji and emoji_mappings:
        html_text_candidate, entities_extra = build_emoji_entities(text, emoji_mappings, category)
        if html_text_candidate != text:
            # html_text_candidate has <tg-emoji> tags
            # For plain text editing we keep text as-is but store html_text for API
            html_text = html_text_candidate
            applied.append(f"emoji_replacement:{len(entities_extra)}")

    # 6. Validate limits
    check_text = html_text or text
    # Strip tags for length check
    plain_for_len = re.sub(r"<[^>]+>", "", check_text) if html_text else text
    ok, err = validate_length(plain_for_len, is_caption)
    if not ok:
        warnings.append(err)
        # revert to original if exceeds limit
        return FormattedMessage(
            text=original, is_caption=is_caption, category=category,
            style_slug=style_slug, changed=False, applied_rules=[], warnings=warnings
        )

    changed = text != original or (html_text is not None and html_text != original)

    return FormattedMessage(
        text=text,
        is_caption=is_caption,
        category=category,
        style_slug=style_slug,
        changed=changed,
        applied_rules=applied,
        warnings=warnings,
        html_text=html_text,
        entities=entities_extra,
    )
