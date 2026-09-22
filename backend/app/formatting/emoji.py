import json
import re
from dataclasses import dataclass

@dataclass
class EmojiMapping:
    unicode_emoji: str
    custom_emoji_id: str
    enabled: bool = True
    contexts: list | None = None
    priority: int = 50

# Default contexts mapping
EMOJI_CONTEXTS = {
    "📢": ["announcement","news"],
    "📚": ["resource","book","education"],
    "🎯": ["planning","goal","consulting"],
    "⏰": ["schedule","deadline","exam"],
    "🔥": ["important","announcement"],
    "💡": ["tip","consulting"],
    "❤️": ["motivational","general"],
    "🎓": ["education","konkur","school"],
    "📝": ["exam","planning"],
    "📌": ["important","consulting"],
    "🔶": ["general"],
    "⭐": ["motivational","rank"],
    "⚡": ["important"],
    "❗": ["announcement"],
}

def should_replace(emoji: str, category: str, mapping: EmojiMapping) -> bool:
    if not mapping.enabled:
        return False
    # Premium: always replace regardless of category (user wants every post premium)
    # Only restrict if contexts explicitly set to non-empty list
    if not mapping.contexts:
        return True
    return category in mapping.contexts

def build_emoji_entities(text: str, mappings: list[EmojiMapping], category: str) -> tuple[str, list[dict]]:
    """Replace unicode emojis with <tg-emoji> tags and return (html_text, entities).
    For Bot API HTML mode we use <tg-emoji emoji-id="ID">emoji</tg-emoji>.
    Also collect custom_emoji entities for non-HTML path.
    """
    entities = []
    # sort by priority desc, length desc
    sorted_maps = sorted(mappings, key=lambda m: (-m.priority, -len(m.unicode_emoji)))
    result = text
    offset_shift = 0
    for m in sorted_maps:
        if not should_replace(m.unicode_emoji, category, m):
            continue
        # find all occurrences
        # need to handle offset correctly
        idx = 0
        new_result_parts = []
        last = 0
        found = False
        while True:
            pos = result.find(m.unicode_emoji, idx)
            if pos == -1:
                break
            found = True
            new_result_parts.append(result[last:pos])
            tag = f'<tg-emoji emoji-id="{m.custom_emoji_id}">{m.unicode_emoji}</tg-emoji>'
            new_result_parts.append(tag)
            # entity for offset tracking (Telegram counts UTF-16 code units)
            # For HTML we don't need manual entities, but keep for logging
            entities.append({"type":"custom_emoji","offset": pos, "length": len(m.unicode_emoji), "custom_emoji_id": m.custom_emoji_id})
            idx = pos + len(m.unicode_emoji)
            last = idx
        if found:
            new_result_parts.append(result[last:])
            result = "".join(new_result_parts)
    return result, entities

def simple_replace(text: str, mappings: list[EmojiMapping], category: str) -> tuple[str, int]:
    """Fallback plain replacement counter without HTML."""
    count = 0
    for m in sorted(mappings, key=lambda x: -x.priority):
        if not should_replace(m.unicode_emoji, category, m):
            continue
        if m.unicode_emoji in text:
            count += text.count(m.unicode_emoji)
    return text, count
