"""Render a draft with the existing library before it is sent.

Custom emoji ids come only from mappings the panel already stored.
"""
from __future__ import annotations

from backend.app.formatting.engine import format_message

LAYOUTS = {"list", "scatter", "closing", "title", "quiet"}


def prepare_publish_payload(
    body: str,
    category: str | None,
    layout: str | None,
    mappings: list | None,
    *,
    is_caption: bool = False,
) -> dict:
    chosen = layout if layout in LAYOUTS else "title"
    if chosen != "quiet":
        chosen = "title"
    quiet = chosen == "quiet"
    result = format_message(
        body or "",
        is_caption=is_caption,
        emoji_mappings=mappings or [],
        enable_emoji=not quiet,
        header_enabled=False,
        category=category or "news",
        emoji_layout="title" if quiet else chosen,
        body_emoji=not quiet,
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
