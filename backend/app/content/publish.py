"""Render a draft with the existing library before it is sent.

Custom emoji ids come only from mappings the panel already stored.
Autopost does not inherit the beautifier's builtin footer. A quiet post
stays quiet. Every other post gets one title emoji from its own spectrum.
"""
from __future__ import annotations

from backend.app.formatting.engine import format_message
from backend.app.formatting.styles import StyleConfig

LAYOUTS = {"list", "scatter", "closing", "title", "quiet"}
_PLAIN = StyleConfig(
    name="پست خودکار",
    slug="autopost",
    divider="",
    use_divider_bottom=False,
    add_footer=False,
    footer_template=None,
)


def prepare_publish_payload(
    body: str,
    category: str | None,
    layout: str | None,
    mappings: list | None,
    *,
    is_caption: bool = False,
    avoid_emoji_ids: set[str] | None = None,
) -> dict:
    chosen = layout if layout in LAYOUTS else "title"
    if chosen != "quiet":
        chosen = "title"
    quiet = chosen == "quiet"
    result = format_message(
        body or "",
        is_caption=is_caption,
        channel_style_slug="autopost",
        footer_text="",
        emoji_mappings=mappings or [],
        enable_emoji=not quiet,
        header_enabled=False,
        category=category or "news",
        emoji_layout="title" if quiet else chosen,
        body_emoji=not quiet,
        avoid_emoji_ids=avoid_emoji_ids,
        style_config=_PLAIN,
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
