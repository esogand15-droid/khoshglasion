"""Render a draft with the existing library before it is sent.

Custom emoji ids come only from mappings the panel already stored.
A quiet post stays quiet. Every other post gets one title emoji from its
own spectrum. The channel footer is whatever the autopost section saved;
an unset footer uses the consultation-channel block.
"""
from __future__ import annotations

from backend.app.formatting.engine import format_message
from backend.app.formatting.styles import DEFAULT_FOOTER, DIVIDER, StyleConfig

LAYOUTS = {"list", "scatter", "closing", "title", "quiet"}
_PLAIN = StyleConfig(
    name="پست خودکار",
    slug="autopost",
    divider="",
    use_divider_bottom=False,
    add_footer=False,
    footer_template=None,
)


def configured_footer(raw: str | None) -> str:
    """None means the consultation footer. An empty string turns it off."""
    if raw is None:
        return DEFAULT_FOOTER
    return raw.strip()


def _chrome(footer: str) -> StyleConfig:
    return StyleConfig(
        name="پست خودکار",
        slug="autopost",
        divider=DIVIDER,
        use_divider_bottom=True,
        add_footer=True,
        footer_template=footer,
    )


def prepare_publish_payload(
    body: str,
    category: str | None,
    layout: str | None,
    mappings: list | None,
    *,
    is_caption: bool = False,
    avoid_emoji_ids: set[str] | None = None,
    footer: str | None = None,
) -> dict:
    chosen = layout if layout in LAYOUTS else "title"
    if chosen != "quiet":
        chosen = "title"
    quiet = chosen == "quiet"
    chrome = (footer or "").strip()
    style = _chrome(chrome) if chrome else _PLAIN
    result = format_message(
        body or "",
        is_caption=is_caption,
        channel_style_slug="autopost",
        footer_text=chrome,
        emoji_mappings=mappings or [],
        enable_emoji=not quiet,
        header_enabled=False,
        category=category or "news",
        emoji_layout="title" if quiet else chosen,
        body_emoji=not quiet,
        avoid_emoji_ids=avoid_emoji_ids,
        style_config=style,
        max_emoji=1,
    )
    entities = list(result.entities or [])
    ids = [
        str(item.get("custom_emoji_id"))
        for item in entities
        if item.get("type") == "custom_emoji" and item.get("custom_emoji_id")
    ]
    return {
        "text": result.text,
        "html_text": result.html_text,
        "entities": entities,
        "emoji_ids": ids,
        "applied": list(result.applied_rules or []),
    }
