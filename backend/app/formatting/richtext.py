"""Keep Telegram formatting while the channel chrome is applied.

The broken test post happened because the webhook's entities were discarded.
A gold-line custom emoji then showed its fallback (⚡), the quote bar
disappeared, and a second footer was appended. On that second footer the
@ of an RTL line flipped to ``Rotbeland_support@``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import html
import re

from backend.app.formatting.emoji import EmojiMapping, emoji_graphemes, find_emoji_spans, first_emoji_grapheme
from backend.app.formatting.templates import (
    DEFAULT_CHANNEL_URL,
    LONG_RULE,
    MEMBERSHIP_TEXT,
    SHORT_RULE,
    branded_footer,
    support_handle,
)
from backend.app.formatting.textutil import URL_RE, utf16_len

GLUED_MENTION = re.compile(
    r"^(.+[\u0600-\u06FF].*?)[ \t]+(@[A-Za-z0-9_]{3,})[ \t]*$"
)
MENTION_LINE = re.compile(r"^[\u200e\u200f]*@[A-Za-z0-9_]{3,}$")
LIGHTNING = {"⚡", "\ufe0f"}
FULL_GOLD_COUNT = 10
MAX_GOLD_COUNT = 18
MAX_CUSTOM_EMOJI = 90
_OPTION_LINE = re.compile(r"(?m)^[ \t]*(?:[1-4۱-۴][).．]|[الفبجد]\))")
_PROTECTED_MARKS = {"blockquote", "expandable_blockquote", "code", "pre"}


@dataclass(frozen=True)
class Mark:
    type: str
    start: int
    end: int
    url: str | None = None
    custom_emoji_id: str | None = None
    collapsed: bool | None = None
    language: str | None = None

    def shift(self, delta: int) -> "Mark":
        return replace(self, start=self.start + delta, end=self.end + delta)


def _py_index(text: str, utf16_offset: int) -> int:
    raw = text.encode("utf-16-le")
    bounded = max(0, min(utf16_offset, len(raw) // 2))
    return len(raw[: bounded * 2].decode("utf-16-le", errors="ignore"))


def parse_telegram_entities(text: str, raw: list | None) -> list[Mark]:
    marks: list[Mark] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "")
        if not kind:
            continue
        start = _py_index(text, int(item.get("offset") or 0))
        end = _py_index(text, int(item.get("offset") or 0) + int(item.get("length") or 0))
        if end <= start or start < 0 or end > len(text):
            continue
        url = item.get("url")
        custom_id = item.get("custom_emoji_id")
        user = item.get("user") or {}
        if kind == "text_mention" and not url and user.get("id"):
            url = f"tg://user?id={user.get('id')}"
        language = item.get("language")
        marks.append(Mark(
            type=kind,
            start=start,
            end=end,
            url=str(url) if url else None,
            custom_emoji_id=str(custom_id) if custom_id else None,
            collapsed=item.get("collapsed"),
            language=str(language) if language else None,
        ))
    return marks


def quote_texts(text: str, raw_entities: list | None) -> list[str]:
    found: list[str] = []
    for mark in parse_telegram_entities(text, raw_entities):
        if mark.type not in {"blockquote", "expandable_blockquote"}:
            continue
        snippet = text[mark.start:mark.end].strip()
        if snippet and snippet not in found:
            found.append(snippet)
    return found


def role_for_raw_entity(text: str, entity: dict) -> str:
    marks = parse_telegram_entities(text, [entity])
    if not marks:
        return "accent"
    return classify_emoji_role(text, marks[0].start, marks[0].end)


def classify_emoji_role(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end]
    if is_divider_line(line) or is_lightning_line(line):
        return "divider"
    if "عضویت" in line:
        return "membership"
    if "رزرو" in line or "خصوصی" in line:
        return "support"
    if _inside_any(start, end, parse_telegram_entities(text, None)):
        return "accent"
    return "accent"


def is_divider_line(line: str) -> bool:
    core = "".join(ch for ch in line.strip() if not ch.isspace())
    if len(core) < 2:
        return False
    for ch in core:
        if ch.isalnum() or "\u0600" <= ch <= "\u06FF":
            return False
    return True


_BIDI = set("\u200c\u200e\u200f\u200d\ufe0f\ufe0e")


def _symbol_core(line: str) -> str:
    return "".join(ch for ch in line.strip() if not ch.isspace() and ch not in _BIDI)


def _has_word_char(core: str) -> bool:
    return any(ch.isalnum() or "\u0600" <= ch <= "\u06FF" for ch in core)


def is_lightning_line(line: str) -> bool:
    core = _symbol_core(line)
    return bool(core) and set(core) <= LIGHTNING


def is_lightning_heavy(line: str) -> bool:
    """A broken gold-line row is often many ⚡ plus one leftover symbol."""
    core = _symbol_core(line)
    if not core or _has_word_char(core):
        return False
    bolts = core.count("⚡")
    return bolts >= 2 or (bolts >= 1 and bolts >= len(core) - 1)


def is_symbol_only_line(line: str) -> bool:
    core = _symbol_core(line)
    return bool(core) and len(core) <= 16 and not _has_word_char(core)


def is_membership_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    return "عضویت" in compact and "کانال" in compact


def is_footer_line(line: str) -> bool:
    compact = re.sub(r"[\s\u200c\u200e\u200f]+", "", line)
    if is_membership_line(line):
        return True
    if "رزرومشاوره" in compact or "مشاورهتخصصیکنکور" in compact:
        return True
    if "Rotbeland_support" in line or MENTION_LINE.match(line.strip()):
        return True
    return False


def has_channel_footer(text: str) -> bool:
    return any(is_membership_line(line) or "Rotbeland_support" in line for line in text.split("\n"))


def shield_quotes(text: str, quotes: list[str]) -> str:
    shielded = text
    for quote in sorted(quotes, key=len, reverse=True):
        if quote and quote in shielded and f"«{quote}»" not in shielded:
            shielded = shielded.replace(quote, f"«{quote}»", 1)
    return shielded


def unwrap_quotes(text: str, quotes: list[str]) -> tuple[str, list[Mark]]:
    """Turn preserved quote strings back into blockquote marks."""
    marks: list[Mark] = []
    updated = text
    for quote in sorted(quotes, key=len, reverse=True):
        if not quote:
            continue
        token = f"«{quote}»"
        pos = updated.find(token)
        if pos >= 0:
            updated = updated[:pos] + quote + updated[pos + len(token):]
            marks.append(Mark("blockquote", pos, pos + len(quote)))
            continue
        pos = updated.find(quote)
        if pos >= 0:
            marks.append(Mark("blockquote", pos, pos + len(quote)))
    return updated, marks


def _line_segments(text: str) -> list[tuple[int, int, str, str]]:
    rows: list[tuple[int, int, str, str]] = []
    cursor = 0
    while cursor <= len(text):
        newline = text.find("\n", cursor)
        if newline < 0:
            rows.append((cursor, len(text), text[cursor:], ""))
            break
        rows.append((cursor, newline, text[cursor:newline], "\n"))
        cursor = newline + 1
        if cursor == len(text):
            break
    return rows


def _first_footer_chrome(lines: list[str]) -> list[str]:
    memberships = [i for i, line in enumerate(lines) if is_membership_line(line)]
    if not memberships:
        return lines
    start = memberships[0]
    while start > 0 and (is_divider_line(lines[start - 1]) or not lines[start - 1].strip()):
        start -= 1
    end = memberships[0] + 1
    while end < len(lines):
        line = lines[end]
        if is_membership_line(line) or is_divider_line(line):
            break
        if is_footer_line(line) or not line.strip() or "@" in line:
            end += 1
            continue
        break
    return lines[start:end]


def _isolate_line(line: str) -> str:
    stripped = line.strip()
    if MENTION_LINE.match(stripped):
        handle = stripped.lstrip("\u200e\u200f")
        return f"\u200e{handle}"
    glued = GLUED_MENTION.match(line.strip())
    if glued:
        return f"{glued.group(1).rstrip()}\n\u200e{glued.group(2)}"
    return line


def _collapse_lightning(line: str, covered: bool) -> str:
    if covered or not (is_lightning_line(line) or is_lightning_heavy(line)):
        return line
    return LONG_RULE


def _covered_by_custom_emoji(start: int, end: int, marks: list[Mark]) -> bool:
    return any(mark.type == "custom_emoji" and mark.start < end and mark.end > start for mark in marks)


def _rebuild(text: str, marks: list[Mark], segments: list[tuple[int, int, str]]) -> tuple[str, list[Mark]]:
    mapping: list[int | None] = [None] * (len(text) + 1)
    parts: list[str] = []
    cursor = 0
    for old_start, old_end, new_text in segments:
        old_slice = text[old_start:old_end]
        if new_text == old_slice:
            for offset in range(len(old_slice) + 1):
                mapping[old_start + offset] = cursor + offset
        parts.append(new_text)
        cursor += len(new_text)
    mapping[len(text)] = mapping[len(text)] if mapping[len(text)] is not None else cursor
    new_text = "".join(parts)
    kept: list[Mark] = []
    for mark in marks:
        if mark.start < 0 or mark.end > len(text):
            continue
        start = mapping[mark.start]
        end = mapping[mark.end]
        if start is None or end is None or end <= start:
            continue
        contiguous = True
        for index in range(mark.start, mark.end + 1):
            expected = start + (index - mark.start)
            if mapping[index] != expected:
                contiguous = False
                break
        if contiguous:
            kept.append(replace(mark, start=start, end=end))
    return new_text, kept


def tidy_existing_chrome(
    text: str,
    marks: list[Mark],
    *,
    keep_lightning: bool = False,
) -> tuple[str, list[Mark], list[str]]:
    """Drop a duplicated footer and stop a glued @ from flipping. Body stays."""
    applied: list[str] = []
    rows = _line_segments(text)
    if not rows:
        return text, marks, applied
    contents = [row[2] for row in rows]
    trailing = 0
    for content, _sep in ((row[2], row[3]) for row in reversed(rows)):
        if content.strip() and not is_footer_line(content) and not is_divider_line(content):
            break
        trailing += 1
    if trailing:
        head = contents[:-trailing]
        chrome = _first_footer_chrome(contents[-trailing:])
        if chrome != contents[-trailing:]:
            applied.append("dedupe_footer")
        contents = head + chrome
    return _rebuild_from_kept(text, marks, rows, contents, applied, keep_lightning=keep_lightning)


def _rebuild_from_kept(
    text: str,
    marks: list[Mark],
    rows: list[tuple[int, int, str, str]],
    kept_contents: list[str],
    applied: list[str],
    *,
    keep_lightning: bool = False,
) -> tuple[str, list[Mark], list[str]]:
    # Map original lines to kept lines by walking and skipping dropped footer duplicates.
    original = [row[2] for row in rows]
    pairs: list[tuple[int, str]] = []
    cursor = 0
    for content in kept_contents:
        while cursor < len(original) and original[cursor] != content:
            cursor += 1
        if cursor < len(original):
            pairs.append((cursor, content))
            cursor += 1
        else:
            pairs.append((-1, content))

    segments: list[tuple[int, int, str]] = []
    consumed = set()
    for row_index, (_start, _end, content, sep) in enumerate(rows):
        match = next((pair for pair in pairs if pair[0] == row_index), None)
        old_start = rows[row_index][0]
        old_end = rows[row_index][1] + len(sep)
        if match is None:
            segments.append((old_start, old_end, ""))
            continue
        consumed.add(row_index)
        new_content = match[1]
        covered = _covered_by_custom_emoji(rows[row_index][0], rows[row_index][1], marks)
        if (
            not keep_lightning
            and (is_lightning_line(content) or is_lightning_heavy(content))
            and not covered
        ):
            new_content = _collapse_lightning(content, False)
            if "restore_divider" not in applied:
                applied.append("restore_divider")
        elif is_footer_line(new_content) or GLUED_MENTION.match(new_content.strip()):
            isolated = _isolate_line(new_content)
            if isolated != new_content and "isolate_mention" not in applied:
                applied.append("isolate_mention")
            new_content = isolated
        last_kept = row_index == pairs[-1][0]
        segments.append((old_start, old_end, new_content if last_kept else new_content + "\n"))
    new_text, new_marks = _rebuild(text, marks, segments)
    return new_text, new_marks, applied


def _is_plain_rule(line: str) -> bool:
    core = "".join(ch for ch in line.strip() if not ch.isspace())
    return len(core) >= 2 and set(core) <= set("━─▬")


def _is_rule_line(content: str) -> bool:
    return is_lightning_line(content) or is_lightning_heavy(content) or _is_plain_rule(content) or is_divider_line(content)


def _is_collapsible_line(content: str) -> bool:
    return _is_rule_line(content) or is_symbol_only_line(content)


def _whole_line_custom(start: int, end: int, marks: list[Mark]) -> bool:
    return any(
        mark.type == "custom_emoji" and mark.custom_emoji_id and mark.start <= start and mark.end >= end
        for mark in marks
    )


def _line_custom(start: int, end: int, marks: list[Mark]) -> Mark | None:
    for mark in marks:
        if mark.type == "custom_emoji" and mark.custom_emoji_id and start <= mark.start < end:
            return mark
    return None


def _is_gold_line(content: str) -> bool:
    return is_lightning_line(content) or is_lightning_heavy(content) or _is_plain_rule(content)


def gold_spark_count(line: str) -> int:
    """A short or broken bar becomes a full row. A long bar keeps its own length."""
    count = len(emoji_graphemes(line or ""))
    if count >= 4:
        return min(count, MAX_GOLD_COUNT)
    return FULL_GOLD_COUNT


def _spark_entities_valid(line: str, line_start: int, marks: list[Mark]) -> bool:
    graphemes = emoji_graphemes(line)
    if len(graphemes) < 4:
        return False
    if any(ch.isalnum() or "\u0600" <= ch <= "\u06FF" for ch in line):
        return False
    line_end = line_start + len(line)
    expected = {(line_start + start, line_start + end) for start, end, _glyph in graphemes}
    seen: set[tuple[int, int]] = set()
    for mark in marks:
        if mark.type != "custom_emoji" or not mark.custom_emoji_id:
            continue
        if mark.end <= line_start or mark.start >= line_end:
            continue
        key = (mark.start, mark.end)
        if key not in expected or not str(mark.custom_emoji_id).isdigit():
            return False
        if utf16_len(line[mark.start - line_start:mark.end - line_start]) > 16:
            return False
        seen.add(key)
    return seen == expected


def _best_divider(mappings: list[EmojiMapping] | None) -> tuple[str, str] | None:
    ranked: list[tuple[int, int, int, str, str]] = []
    for mapping in mappings or []:
        if not mapping.enabled or not str(mapping.custom_emoji_id).isdigit() or not mapping.unicode_emoji:
            continue
        tagged = (mapping.category or "") == "divider"
        glyph = first_emoji_grapheme(mapping.unicode_emoji)
        inferred = is_lightning_line(mapping.unicode_emoji) or _is_plain_rule(mapping.unicode_emoji)
        if glyph and is_lightning_line(glyph):
            inferred = True
        if not tagged and not inferred:
            continue
        ranked.append((
            2 if glyph else 0,
            1 if tagged else 0,
            int(mapping.priority or 0),
            mapping.unicode_emoji,
            str(mapping.custom_emoji_id),
        ))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return ranked[0][3], ranked[0][4]


def _best_spark(mappings: list[EmojiMapping] | None) -> tuple[str, str] | None:
    chosen = _best_divider(mappings)
    if not chosen:
        return None
    glyph = first_emoji_grapheme(chosen[0])
    if not glyph:
        return None
    return glyph, chosen[1]


def _spark_from_line(content: str, marks: list[Mark], start: int, end: int) -> tuple[str, str] | None:
    """Reuse a document id already on the line. Never invent one."""
    glyph = first_emoji_grapheme(content)
    if not glyph:
        return None
    for mark in marks:
        if (
            mark.type == "custom_emoji"
            and mark.custom_emoji_id
            and str(mark.custom_emoji_id).isdigit()
            and start <= mark.start < end
        ):
            return glyph, str(mark.custom_emoji_id)
    return None


def infer_dividers(mappings: list[EmojiMapping] | None) -> list[tuple[str, str]]:
    chosen = _best_divider(mappings)
    return [chosen] if chosen else []


def apply_divider_library(
    text: str,
    marks: list[Mark],
    mappings: list[EmojiMapping] | None,
) -> tuple[str, list[Mark], list[str]]:
    """Turn a gold line into separate premium sparks.

    One custom-emoji entity must cover one spark. A single entity over
    ⚡⚡⚡ is what leaves two sparks premium and the rest broken. Consecutive
    gold bars still collapse to one row, not two.
    """
    if not text:
        return text, marks, []
    rows = _line_segments(text)
    if not rows:
        return text, marks, []
    library = _best_spark(mappings)
    skip_rows: set[int] = set()
    replacements: dict[int, tuple[str, str | None, int]] = {}
    applied: list[str] = []
    index = 0
    while index < len(rows):
        if not _is_gold_line(rows[index][2]):
            index += 1
            continue
        end = index + 1
        while end < len(rows) and (_is_gold_line(rows[end][2]) or not rows[end][2].strip()):
            end += 1
        while end > index + 1 and not rows[end - 1][2].strip():
            end -= 1
        rule_indexes = [i for i in range(index, end) if rows[i][2].strip()]
        first = rule_indexes[0]
        content = rows[first][2]
        if len(rule_indexes) == 1 and _spark_entities_valid(content, rows[first][0], marks):
            index = end
            continue
        spark = library or _spark_from_line(content, marks, rows[first][0], rows[first][1])
        if spark:
            glyph, custom_id = spark
            count = max(gold_spark_count(rows[i][2]) for i in rule_indexes)
            fallback = glyph * count
            glyph_len = len(glyph)
        else:
            fallback, custom_id, glyph_len = LONG_RULE, None, 0
        replacements[first] = (fallback, custom_id, glyph_len)
        for row_index in range(first + 1, end):
            skip_rows.add(row_index)
        applied.append("apply_divider_emoji" if custom_id else "collapse_divider")
        if custom_id:
            applied.append(f"gold_row:{fallback.count(glyph) if spark else 0}")
        index = end
    if not replacements:
        return text, marks, []

    segments: list[tuple[int, int, str]] = []
    inserted: list[tuple[int, str, str | None, int]] = []
    new_cursor = 0
    for row_index, (old_start, old_end, content, sep) in enumerate(rows):
        old_limit = old_end + len(sep)
        if row_index in skip_rows:
            segments.append((old_start, old_limit, ""))
            continue
        if row_index in replacements:
            fallback, custom_id, glyph_len = replacements[row_index]
            following = any(i > row_index and i not in skip_rows for i in range(len(rows)))
            suffix = "\n" if following else ""
            segments.append((old_start, old_limit, fallback + suffix))
            if custom_id and glyph_len:
                inserted.append((new_cursor, fallback, custom_id, glyph_len))
            new_cursor += len(fallback + suffix)
            continue
        piece = content + sep
        segments.append((old_start, old_limit, piece))
        new_cursor += len(piece)
    updated, kept = _rebuild(text, marks, segments)
    extra: list[Mark] = []
    for start, fallback, custom_id, glyph_len in inserted:
        if not custom_id or glyph_len <= 0:
            continue
        if start < 0 or start + len(fallback) > len(updated) or updated[start:start + len(fallback)] != fallback:
            continue
        if len(fallback) % glyph_len != 0:
            continue
        for offset in range(0, len(fallback), glyph_len):
            extra.append(Mark("custom_emoji", start + offset, start + offset + glyph_len, custom_emoji_id=custom_id))
    if extra:
        kept = [
            mark for mark in kept
            if mark.type != "custom_emoji" or not any(not (mark.end <= item.start or mark.start >= item.end) for item in extra)
        ]
    return updated, kept + extra, applied


def _role_emoji(mappings: list[EmojiMapping] | None, role: str) -> tuple[str, str] | None:
    for mapping in sorted(mappings or [], key=lambda item: -item.priority):
        if (mapping.category or "") != role or not mapping.enabled:
            continue
        glyph = first_emoji_grapheme(mapping.unicode_emoji or "")
        if str(mapping.custom_emoji_id).isdigit() and glyph:
            return glyph, str(mapping.custom_emoji_id)
    return None


def append_missing_chrome(
    text: str,
    marks: list[Mark],
    *,
    add_footer: bool,
    add_divider: bool,
    footer_text: str | None,
    footer_url: str | None,
    support_username: str | None,
    mappings: list[EmojiMapping] | None,
) -> tuple[str, list[Mark], list[str]]:
    applied: list[str] = []
    updated = text.rstrip()
    mark_list = list(marks)
    has_divider = any(is_divider_line(line) or is_lightning_line(line) for line in updated.split("\n"))
    has_footer = has_channel_footer(updated)
    if add_divider and not has_divider:
        spark = _best_spark(mappings)
        if spark:
            glyph, custom_id = spark
            row = glyph * FULL_GOLD_COUNT
            prefix = updated + "\n\n"
            updated = prefix + row
            for offset in range(0, len(row), len(glyph)):
                mark_list.append(Mark(
                    "custom_emoji",
                    len(prefix) + offset,
                    len(prefix) + offset + len(glyph),
                    custom_emoji_id=custom_id,
                ))
            applied.append("add_divider_emoji")
            applied.append(f"gold_row:{FULL_GOLD_COUNT}")
        else:
            updated = updated + "\n\n" + LONG_RULE
            applied.append("add_divider")
        has_divider = True
    if add_footer and not has_footer:
        footer = (footer_text or "").strip() or branded_footer(support_username)
        footer = "\n".join(_isolate_line(line) for line in footer.split("\n"))
        membership = _role_emoji(mappings, "membership")
        support = _role_emoji(mappings, "support")
        if membership and MEMBERSHIP_TEXT in footer and membership[0] not in footer:
            footer = footer.replace(MEMBERSHIP_TEXT, f"{membership[0]} {MEMBERSHIP_TEXT}", 1)
        if support and "رزرو مشاوره" in footer and support[0] not in footer:
            footer = footer.replace("رزرو مشاوره خصوصی:", f"رزرو مشاوره خصوصی: {support[0]}", 1)
        prefix = updated.rstrip() + "\n\n"
        updated = prefix + footer.strip()
        applied.append("add_footer")
        if membership and membership[0] in updated[len(prefix):]:
            pos = updated.find(membership[0], len(prefix))
            mark_list.append(Mark("custom_emoji", pos, pos + len(membership[0]), custom_emoji_id=membership[1]))
        if support and support[0] in updated[len(prefix):]:
            pos = updated.find(support[0], len(prefix))
            mark_list.append(Mark("custom_emoji", pos, pos + len(support[0]), custom_emoji_id=support[1]))
    url = (footer_url or DEFAULT_CHANNEL_URL).strip()
    if url and MEMBERSHIP_TEXT in updated and not any(mark.type == "text_link" and mark.url == url for mark in mark_list):
        pos = updated.find(MEMBERSHIP_TEXT)
        if pos >= 0 and not any(mark.type == "text_link" and mark.start <= pos < mark.end for mark in mark_list):
            mark_list.append(Mark("text_link", pos, pos + len(MEMBERSHIP_TEXT), url=url))
            applied.append("membership_link")
    return updated, mark_list, applied


def decorate_existing_footer(
    text: str,
    marks: list[Mark],
    mappings: list[EmojiMapping] | None,
) -> tuple[str, list[Mark], list[str]]:
    """Put captured footer emoji on the existing membership and support lines."""
    if not text or not mappings:
        return text, marks, []
    updated = text
    current = list(marks)
    applied: list[str] = []

    def insert(role: str, needle: str, rule: str) -> None:
        nonlocal updated, current
        emoji = _role_emoji(mappings, role)
        if not emoji:
            return
        pos = updated.find(needle)
        if pos < 0:
            return
        line_start = updated.rfind("\n", 0, pos) + 1
        line_end = updated.find("\n", pos)
        if line_end < 0:
            line_end = len(updated)
        line = updated[line_start:line_end]
        if emoji[0] in line:
            if not any(mark.type == "custom_emoji" and line_start <= mark.start < line_end for mark in current):
                found = line.find(emoji[0])
                if found >= 0:
                    start = line_start + found
                    current.append(Mark("custom_emoji", start, start + len(emoji[0]), custom_emoji_id=emoji[1]))
                    applied.append(rule)
            return
        updated = updated[:line_start] + emoji[0] + " " + updated[line_start:]
        delta = len(emoji[0]) + 1
        current = [mark.shift(delta) if mark.start >= line_start else mark for mark in current]
        current.append(Mark("custom_emoji", line_start, line_start + len(emoji[0]), custom_emoji_id=emoji[1]))
        applied.append(rule)

    insert("membership", MEMBERSHIP_TEXT, "apply_membership_emoji")
    insert("support", "رزرو مشاوره", "apply_support_emoji")
    return updated, current, applied


def _inside_any(start: int, end: int, marks: list[Mark]) -> bool:
    return any(mark.start <= start and end <= mark.end for mark in marks)


def _protected_ranges(text: str, marks: list[Mark]) -> list[tuple[int, int]]:
    """Quotes, code and exam options must not have their emoji swapped."""
    ranges = [(mark.start, mark.end) for mark in marks if mark.type in _PROTECTED_MARKS]
    for match in _OPTION_LINE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end < 0:
            line_end = len(text)
        ranges.append((line_start, line_end))
    return ranges


def add_library_emoji(
    text: str,
    marks: list[Mark],
    mappings: list[EmojiMapping] | None,
    category: str,
    max_emoji: int,
    avoid_ids: set[str] | None = None,
) -> list[Mark]:
    if not mappings or max_emoji <= 0:
        return marks
    usable = [item for item in mappings if (item.category or "") != "divider"]
    spans = find_emoji_spans(text, usable, category, max_emoji=max_emoji, force=False, avoid_ids=avoid_ids)
    occupied = [(mark.start, mark.end) for mark in marks]
    protected = _protected_ranges(text, marks)
    extra = list(marks)
    for start, end, _emoji, custom_id in spans:
        if any(not (end <= left or start >= right) for left, right in occupied):
            continue
        if any(not (end <= left or start >= right) for left, right in protected):
            continue
        if _inside_url(text, start):
            continue
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        line = text[line_start: len(text) if line_end < 0 else line_end]
        if is_divider_line(line):
            continue
        extra.append(Mark("custom_emoji", start, end, custom_emoji_id=custom_id))
        occupied.append((start, end))
        if sum(1 for mark in extra if mark.type == "custom_emoji") >= max_emoji:
            break
    return extra


def _inside_url(text: str, pos: int) -> bool:
    return any(match.start() <= pos < match.end() for match in URL_RE.finditer(text))


_OPEN = {
    "bold": "<b>",
    "italic": "<i>",
    "underline": "<u>",
    "strikethrough": "<s>",
    "spoiler": "<tg-spoiler>",
    "code": "<code>",
    "pre": "<pre>",
    "blockquote": "<blockquote>",
    "expandable_blockquote": "<blockquote expandable>",
}
_CLOSE = {
    "bold": "</b>",
    "italic": "</i>",
    "underline": "</u>",
    "strikethrough": "</s>",
    "spoiler": "</tg-spoiler>",
    "code": "</code>",
    "pre": "</pre>",
    "blockquote": "</blockquote>",
    "expandable_blockquote": "</blockquote>",
}
_LANG = re.compile(r"^[A-Za-z0-9_+-]{1,32}$")


def _pre_language(mark: Mark) -> str | None:
    lang = (mark.language or "").strip()
    return lang if _LANG.fullmatch(lang) else None


def _open_tag(mark: Mark) -> str:
    if mark.type == "text_link" and mark.url:
        return f'<a href="{html.escape(mark.url, quote=True)}">'
    if mark.type == "text_mention" and mark.url:
        return f'<a href="{html.escape(mark.url, quote=True)}">'
    if mark.type == "custom_emoji" and mark.custom_emoji_id and str(mark.custom_emoji_id).isdigit():
        return f'<tg-emoji emoji-id="{html.escape(mark.custom_emoji_id, quote=True)}">'
    if mark.type == "pre":
        lang = _pre_language(mark)
        if lang:
            return f'<pre><code class="language-{html.escape(lang, quote=True)}">'
        return "<pre>"
    return _OPEN.get(mark.type, "")


def _close_tag(mark: Mark) -> str:
    if mark.type in {"text_link", "text_mention"} and mark.url:
        return "</a>"
    if mark.type == "custom_emoji" and mark.custom_emoji_id:
        return "</tg-emoji>"
    if mark.type == "pre" and _pre_language(mark):
        return "</code></pre>"
    return _CLOSE.get(mark.type, "")


def render_html(text: str, marks: list[Mark]) -> str | None:
    meaningful = [mark for mark in marks if _open_tag(mark) and mark.end > mark.start]
    if not meaningful:
        return None
    events = []
    for index, mark in enumerate(meaningful):
        length = mark.end - mark.start
        events.append((mark.start, 1, -length, index, "open", mark))
        events.append((mark.end, 0, length, index, "close", mark))
    events.sort()
    parts: list[str] = []
    cursor = 0
    for pos, _kind, _length, _index, action, mark in events:
        if pos < cursor:
            continue
        if pos > cursor:
            parts.append(html.escape(text[cursor:pos]))
            cursor = pos
        parts.append(_open_tag(mark) if action == "open" else _close_tag(mark))
    parts.append(html.escape(text[cursor:]))
    rendered = "".join(parts)
    return rendered if "<" in rendered else None


def marks_to_dicts(marks: list[Mark]) -> list[dict]:
    return [
        {
            "type": mark.type,
            "offset": mark.start,
            "length": mark.end - mark.start,
            "url": mark.url,
            "custom_emoji_id": mark.custom_emoji_id,
            "language": mark.language,
        }
        for mark in marks
        if mark.end > mark.start
    ]


def emoji_spans(marks: list[Mark]) -> list[tuple[int, int, str]]:
    return [
        (mark.start, mark.end, mark.custom_emoji_id)
        for mark in marks
        if mark.type == "custom_emoji" and mark.custom_emoji_id
    ]


def strip_custom_emoji_html(html_text: str) -> str:
    return re.sub(r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>", r"\1", html_text or "", flags=re.DOTALL)


ACCENT_CHOICES = {
    "announcement": ("📢", "🚨", "🔔", "❗", "🔥"),
    "news": ("📌", "ℹ️", "📢", "🔔"),
    "registration": ("✅", "🆕", "📌", "🎓"),
    "exam": ("🎯", "📝", "📚"),
    "rank": ("🏆", "📈", "⭐", "👑"),
    "resource": ("📚", "💡", "📝", "🔖"),
    "lesson": ("📚", "💡", "✏️"),
    "motivational": ("✨", "💪", "🔥", "⭐"),
    "consulting": ("💡", "📌", "✨", "💬"),
    "discount": ("🎁", "🔥", "✅"),
    "planning": ("📅", "📝", "📌"),
    "general": ("✨", "📌", "💡", "🔥", "⭐", "✅"),
}
_LISTISH = re.compile(r"^\s*(?:[•▪·🔹🔶\-–—]|[0-9۰-۹]{1,2}[).．]|[الفبجد]\))")


def _insertable(emoji: str) -> bool:
    return bool(emoji) and not _has_word_char(emoji)


def _line_starts_with_emoji(line: str) -> bool:
    core = line.strip()
    if not core:
        return False
    first = core[0]
    return not (first.isalnum() or "\u0600" <= first <= "\u06FF" or first in "«\"'([")


def accent_pool(mappings: list[EmojiMapping] | None, category: str, avoid_ids: set[str] | None) -> list[EmojiMapping]:
    from backend.app.formatting.spectrum import spectrum_of

    avoided = {str(item) for item in (avoid_ids or set())}
    wanted = spectrum_of(category)
    usable: list[EmojiMapping] = []
    for mapping in mappings or []:
        if not mapping.enabled or not str(mapping.custom_emoji_id).isdigit() or not _insertable(mapping.unicode_emoji or ""):
            continue
        if (mapping.category or "") in {"divider", "membership", "support"}:
            continue
        if not (mapping.category or "").strip() or spectrum_of(mapping.category) != wanted:
            continue
        usable.append(mapping)
    if not usable:
        return []
    preferred = ACCENT_CHOICES.get(wanted) or ACCENT_CHOICES.get(category) or ()
    preferred_rows = [item for item in usable if item.unicode_emoji in preferred]
    pool = preferred_rows or usable
    pool.sort(key=lambda item: (str(item.custom_emoji_id) in avoided, -(item.priority or 0)))
    unique: list[EmojiMapping] = []
    seen: set[str] = set()
    for item in pool:
        if item.unicode_emoji in seen:
            continue
        seen.add(item.unicode_emoji)
        unique.append(item)
    return unique[:2]


def _protected_line(start: int, end: int, marks: list[Mark]) -> bool:
    return any(mark.type in _PROTECTED_MARKS and mark.start < end and mark.end > start for mark in marks)


def plan_placements(indexes: list[int], layout: str, max_insert: int) -> list[tuple[int, str]]:
    """Spread a few accents through the post. Never every line, never only the footer."""
    if not indexes or max_insert <= 0:
        return []
    planned: list[tuple[int, str]] = [(indexes[0], "heading")]
    rest = indexes[1:]
    if layout == "list":
        step = 2 if len(rest) > 3 else 1
        for offset, index in enumerate(rest):
            if offset % step != 0:
                continue
            if planned and index <= planned[-1][0] + 1 and len(rest) > 2:
                continue
            planned.append((index, "point"))
            if len(planned) >= max_insert:
                break
    elif layout == "scatter" and rest and max_insert > 1:
        planned.append((rest[len(rest) // 2], "point"))
        if len(rest) > 2 and max_insert > 2:
            planned.append((rest[-1], "close"))
    elif layout == "closing" and rest and max_insert > 1:
        planned.append((rest[-1], "close"))
    seen: set[int] = set()
    unique: list[tuple[int, str]] = []
    for index, role in planned:
        if index in seen:
            continue
        seen.add(index)
        unique.append((index, role))
    return unique[:max_insert]


def decorate_body(
    text: str,
    marks: list[Mark],
    mappings: list[EmojiMapping] | None,
    *,
    category: str,
    layout: str,
    avoid_ids: set[str] | None,
    max_insert: int,
) -> tuple[str, list[Mark], list[str]]:
    """Put real library emoji on the title and spaced body lines. Words stay."""
    if layout not in {"title", "scatter", "list", "closing"} or max_insert <= 0 or not text:
        return text, marks, []
    pool = accent_pool(mappings, category, avoid_ids)
    if not pool:
        return text, marks, []
    rows = _line_segments(text)
    content_indexes: list[int] = []
    for index, (_start, _end, content, _sep) in enumerate(rows):
        if not content.strip() or is_footer_line(content) or _is_collapsible_line(content):
            continue
        if _protected_line(rows[index][0], rows[index][1], marks) or _OPTION_LINE.search(content):
            continue
        if content.strip().startswith("#") or content.strip().startswith("http"):
            continue
        content_indexes.append(index)
    if not content_indexes:
        return text, marks, []
    placed = plan_placements(content_indexes, layout, max_insert)
    targets = [index for index, _role in placed]
    roles = {index: role for index, role in placed}
    updated = text
    current = list(marks)
    applied: list[str] = []
    for offset, index in enumerate(reversed(targets)):
        start, end, content, _sep = rows[index]
        role = roles.get(index, "point")
        if _line_starts_with_emoji(content) and role != "close":
            continue
        accent = pool[(len(targets) - 1 - offset) % len(pool)]
        emoji = first_emoji_grapheme(accent.unicode_emoji or "") or ""
        if not emoji:
            continue
        if role == "close":
            prefix_at = end
            insert = " " + emoji
            mark_start = end + 1
        else:
            prefix_at = start
            insert = emoji + " "
            mark_start = start
        updated = updated[:prefix_at] + insert + updated[prefix_at:]
        delta = len(insert)
        current = [mark.shift(delta) if mark.start >= prefix_at else mark for mark in current]
        current.append(Mark("custom_emoji", mark_start, mark_start + len(emoji), custom_emoji_id=str(accent.custom_emoji_id)))
        if "body_emoji" not in applied:
            applied.append("body_emoji")
            applied.append("emoji_plan:" + ",".join(role for _index, role in placed))
    return updated, current, applied


def _exact_custom_cover(start: int, end: int, marks: list[Mark]) -> bool:
    return any(
        mark.type == "custom_emoji"
        and mark.custom_emoji_id
        and str(mark.custom_emoji_id).isdigit()
        and mark.start == start
        and mark.end == end
        for mark in marks
    )


def _library_match(grapheme: str, mappings: list[EmojiMapping] | None, category: str | None = None) -> tuple[str, str] | None:
    from backend.app.formatting.spectrum import spectrum_of

    norm = grapheme.replace("\ufe0f", "").replace("\ufe0e", "")
    wanted = spectrum_of(category) if category else None
    best: tuple[int, bool, str, str] | None = None
    for mapping in mappings or []:
        if not mapping.enabled or not str(mapping.custom_emoji_id).isdigit():
            continue
        mapped = (mapping.category or "").strip()
        if wanted and mapped and mapped not in {"divider", "membership", "support"} and spectrum_of(mapped) != wanted:
            continue
        glyph = first_emoji_grapheme(mapping.unicode_emoji or "")
        if not glyph:
            continue
        glyph_norm = glyph.replace("\ufe0f", "").replace("\ufe0e", "")
        if glyph_norm != norm and (mapping.unicode_emoji or "") != grapheme:
            continue
        rank = (int(mapping.priority or 0), glyph == grapheme)
        if best is None or rank > (best[0], best[1]):
            best = (rank[0], rank[1], glyph, str(mapping.custom_emoji_id))
    if not best:
        return None
    return best[2], best[3]


def _substitution_pool(
    mappings: list[EmojiMapping] | None,
    avoid_ids: set[str] | None,
    category: str | None = None,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for item in accent_pool(mappings, category or "general", avoid_ids):
        glyph = first_emoji_grapheme(item.unicode_emoji or "")
        if glyph and str(item.custom_emoji_id).isdigit():
            rows.append((glyph, str(item.custom_emoji_id)))
    return rows


def _span_protected(text: str, start: int, end: int, marks: list[Mark]) -> bool:
    if any(mark.type in _PROTECTED_MARKS and mark.start < end and mark.end > start for mark in marks):
        return True
    line_end = text.find("\n", start)
    if line_end < 0:
        line_end = len(text)
    line_start = text.rfind("\n", 0, start) + 1
    return bool(_OPTION_LINE.search(text[line_start:line_end]))


def _splice_emoji(
    text: str,
    marks: list[Mark],
    start: int,
    end: int,
    glyph: str,
    custom_id: str | None,
) -> tuple[str, list[Mark]]:
    delta = len(glyph) - (end - start)
    updated = text[:start] + glyph + text[end:]
    kept: list[Mark] = []
    for mark in marks:
        if mark.type == "custom_emoji" and mark.start < end and mark.end > start:
            continue
        if mark.end <= start:
            kept.append(mark)
            continue
        if mark.start >= end:
            kept.append(mark.shift(delta))
            continue
        new_end = mark.end + delta if mark.end >= end else mark.end
        if new_end > mark.start:
            kept.append(replace(mark, end=new_end))
    if custom_id and glyph:
        kept.append(Mark("custom_emoji", start, start + len(glyph), custom_emoji_id=custom_id))
    return updated, kept


def premiumize_existing_emoji(
    text: str,
    marks: list[Mark],
    mappings: list[EmojiMapping] | None,
    avoid_ids: set[str] | None = None,
    category: str | None = None,
) -> tuple[str, list[Mark], list[str]]:
    """Replace every unprotected unicode emoji with a saved premium id.

    Quotes, code and exam options keep their glyphs. Nothing here invents an id.
    If no saved id can cover a body emoji, that glyph is removed instead of sent.
    """
    if not text:
        return text, marks, []
    pool = _substitution_pool(mappings, avoid_ids, category)
    spans = emoji_graphemes(text)
    if not spans:
        return text, marks, []
    updated = text
    current = list(marks)
    replaced = 0
    stripped = 0
    sub_index = 0
    custom_count = sum(1 for mark in current if mark.type == "custom_emoji")
    for start, end, grapheme in reversed(spans):
        if _exact_custom_cover(start, end, current):
            continue
        if _inside_url(updated, start) or _span_protected(updated, start, end, current):
            continue
        match = _library_match(grapheme, mappings, category)
        glyph, custom_id = "", None
        if match and custom_count < MAX_CUSTOM_EMOJI:
            glyph, custom_id = match
        elif pool and custom_count < MAX_CUSTOM_EMOJI:
            glyph, custom_id = pool[sub_index % len(pool)]
            sub_index += 1
        updated, current = _splice_emoji(updated, current, start, end, glyph, custom_id)
        if custom_id:
            replaced += 1
            custom_count += 1
        else:
            stripped += 1
    applied: list[str] = []
    if replaced:
        applied.append(f"premium_emoji:{replaced}")
    if stripped:
        applied.append(f"emoji_stripped:{stripped}")
    return updated, current, applied


def prepare_post(
    text: str,
    raw_entities: list | None = None,
    parsed_marks: list[Mark] | None = None,
    *,
    add_footer: bool = True,
    add_divider: bool = True,
    footer_text: str | None = None,
    footer_url: str | None = None,
    support_username: str | None = None,
    mappings: list[EmojiMapping] | None = None,
    category: str = "general",
    max_emoji: int = 12,
    enable_emoji: bool = True,
    body_emoji: bool = True,
    avoid_emoji_ids: set[str] | None = None,
    emoji_layout: str = "title",
) -> tuple[str, str | None, list[dict], list[tuple[int, int, str]], list[str]]:
    marks = list(parsed_marks) if parsed_marks is not None else parse_telegram_entities(text or "", raw_entities)
    updated, marks, applied = tidy_existing_chrome(text or "", marks, keep_lightning=bool(enable_emoji))
    if enable_emoji:
        updated, marks, divider_rules = apply_divider_library(updated, marks, mappings)
        applied.extend(divider_rules)
    updated, marks, extra = append_missing_chrome(
        updated,
        marks,
        add_footer=add_footer,
        add_divider=add_divider,
        footer_text=footer_text,
        footer_url=footer_url,
        support_username=support_username,
        mappings=mappings if enable_emoji else None,
    )
    applied.extend(extra)
    if enable_emoji:
        updated, marks, role_rules = decorate_existing_footer(updated, marks, mappings)
        applied.extend(role_rules)
    if enable_emoji and body_emoji:
        budget = 1 if emoji_layout in {"title", "quiet", "closing"} else min(2, max_emoji)
        updated, marks, accent_rules = decorate_body(
            updated,
            marks,
            mappings,
            category=category,
            layout=emoji_layout,
            avoid_ids=avoid_emoji_ids,
            max_insert=budget,
        )
        applied.extend(accent_rules)
    if enable_emoji:
        before = len([mark for mark in marks if mark.type == "custom_emoji"])
        marks = add_library_emoji(updated, marks, mappings, category, max_emoji, avoid_ids=avoid_emoji_ids)
        after = len([mark for mark in marks if mark.type == "custom_emoji"])
        if after > before:
            applied.append(f"emoji_replacement:{after - before}")
        updated, marks, premium_rules = premiumize_existing_emoji(
            updated, marks, mappings, avoid_emoji_ids, category,
        )
        applied.extend(premium_rules)
    html_text = render_html(updated, marks)
    if html_text and "blockquote" in html_text and "preserve_quote" not in applied:
        applied.append("preserve_quote")
    return updated, html_text, marks_to_dicts(marks), emoji_spans(marks), applied
