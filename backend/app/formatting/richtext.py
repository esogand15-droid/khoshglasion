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

from backend.app.formatting.emoji import EmojiMapping, find_emoji_spans
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


def is_lightning_line(line: str) -> bool:
    core = "".join(ch for ch in line.strip() if not ch.isspace())
    return bool(core) and set(core) <= LIGHTNING


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
    if covered or not is_lightning_line(line):
        return line
    return f"{LONG_RULE}\n{SHORT_RULE}"


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


def tidy_existing_chrome(text: str, marks: list[Mark]) -> tuple[str, list[Mark], list[str]]:
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
    return _rebuild_from_kept(text, marks, rows, contents, applied)


def _rebuild_from_kept(
    text: str,
    marks: list[Mark],
    rows: list[tuple[int, int, str, str]],
    kept_contents: list[str],
    applied: list[str],
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
        if is_lightning_line(content) and not covered:
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


def infer_dividers(mappings: list[EmojiMapping] | None) -> list[tuple[str, str]]:
    tagged = _divider_ids(mappings)
    if tagged:
        return tagged
    inferred: list[tuple[str, str]] = []
    for mapping in mappings or []:
        if not mapping.enabled or not str(mapping.custom_emoji_id).isdigit() or not mapping.unicode_emoji:
            continue
        if is_lightning_line(mapping.unicode_emoji) or _is_plain_rule(mapping.unicode_emoji):
            item = (mapping.unicode_emoji, str(mapping.custom_emoji_id))
            if item not in inferred:
                inferred.append(item)
    return inferred[:2]


def apply_divider_library(
    text: str,
    marks: list[Mark],
    mappings: list[EmojiMapping] | None,
) -> tuple[str, list[Mark], list[str]]:
    """Turn a degraded ⚡ row, or a plain ━ rule, into the captured gold-line emoji.

    A forwarded divider is often one custom emoji whose fallback is ⚡. Leaving
    the fallback in place is why the test post showed a lightning row.
    """
    dividers = infer_dividers(mappings)
    if not dividers or not text:
        return text, marks, []
    rows = _line_segments(text)
    if not rows:
        return text, marks, []
    skip_rows: set[int] = set()
    replacements: dict[int, str] = {}
    applied: list[str] = []
    index = 0
    while index < len(rows):
        content = rows[index][2]
        covered = _covered_by_custom_emoji(rows[index][0], rows[index][1], marks)
        degraded = not covered and (is_lightning_line(content) or _is_plain_rule(content))
        if not degraded:
            index += 1
            continue
        end = index + 1
        while end < len(rows):
            nxt = rows[end][2]
            nxt_covered = _covered_by_custom_emoji(rows[end][0], rows[end][1], marks)
            if nxt_covered or not (is_lightning_line(nxt) or _is_plain_rule(nxt) or not nxt.strip()):
                break
            end += 1
        while end > index + 1 and not rows[end - 1][2].strip():
            end -= 1
        block = "\n".join(fallback for fallback, _cid in dividers)
        replacements[index] = block
        for row_index in range(index + 1, end):
            skip_rows.add(row_index)
        applied.append("apply_divider_emoji")
        index = end
    if not replacements:
        return text, marks, []

    segments: list[tuple[int, int, str]] = []
    inserted: list[tuple[int, list[tuple[str, str]]]] = []
    new_cursor = 0
    for row_index, (old_start, old_end, content, sep) in enumerate(rows):
        old_limit = old_end + len(sep)
        if row_index in skip_rows:
            segments.append((old_start, old_limit, ""))
            continue
        if row_index in replacements:
            block = replacements[row_index]
            last = row_index == len(rows) - 1 and not skip_rows
            suffix = "" if last else "\n"
            segments.append((old_start, old_limit, block + suffix))
            inserted.append((new_cursor, dividers))
            new_cursor += len(block + suffix)
            continue
        piece = content + sep
        segments.append((old_start, old_limit, piece))
        new_cursor += len(piece)
    updated, kept = _rebuild(text, marks, segments)
    # Marks for the inserted emoji are computed against the rebuilt string.
    extra: list[Mark] = []
    for start, pairs in inserted:
        # The recorded cursor was an estimate; locate the block we just wrote.
        block = "\n".join(fallback for fallback, _cid in pairs)
        pos = updated.find(block, max(0, start - 4))
        if pos < 0:
            pos = updated.find(block)
        if pos < 0:
            continue
        cursor = pos
        for fallback, custom_id in pairs:
            extra.append(Mark("custom_emoji", cursor, cursor + len(fallback), custom_emoji_id=custom_id))
            cursor += len(fallback) + 1
    return updated, kept + extra, applied


def _divider_ids(mappings: list[EmojiMapping] | None) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for mapping in mappings or []:
        if (mapping.category or "") != "divider":
            continue
        if not mapping.enabled or not str(mapping.custom_emoji_id).isdigit():
            continue
        item = (mapping.unicode_emoji, str(mapping.custom_emoji_id))
        if item not in found:
            found.append(item)
    return found[:2]


def _role_emoji(mappings: list[EmojiMapping] | None, role: str) -> tuple[str, str] | None:
    for mapping in sorted(mappings or [], key=lambda item: -item.priority):
        if (mapping.category or "") != role or not mapping.enabled:
            continue
        if str(mapping.custom_emoji_id).isdigit() and mapping.unicode_emoji:
            return mapping.unicode_emoji, str(mapping.custom_emoji_id)
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
    trailing = [line for line in updated.split("\n")[-6:]]
    has_divider = any(is_divider_line(line) or is_lightning_line(line) for line in trailing)
    has_footer = has_channel_footer(updated)
    if add_divider and not has_divider:
        dividers = infer_dividers(mappings)
        if dividers:
            lines = []
            for fallback, custom_id in (dividers if len(dividers) > 1 else dividers * 2):
                start = len(updated) + 2 + sum(len(line) + 1 for line in lines)
                # recompute after join below
                lines.append((fallback, custom_id))
            block = "\n".join(item[0] for item in lines)
            prefix = updated + "\n\n"
            updated = prefix + block
            cursor = len(prefix)
            for fallback, custom_id in lines:
                mark_list.append(Mark("custom_emoji", cursor, cursor + len(fallback), custom_emoji_id=custom_id))
                cursor += len(fallback) + 1
            applied.append("add_divider_emoji")
        else:
            updated = updated + "\n\n" + f"{LONG_RULE}\n{SHORT_RULE}"
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
    if not spans:
        spans = find_emoji_spans(text, usable, category, max_emoji=max_emoji, force=True, avoid_ids=avoid_ids)
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
) -> tuple[str, str | None, list[dict], list[tuple[int, int, str]], list[str]]:
    marks = list(parsed_marks) if parsed_marks is not None else parse_telegram_entities(text or "", raw_entities)
    updated, marks, applied = tidy_existing_chrome(text or "", marks)
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
        before = len([mark for mark in marks if mark.type == "custom_emoji"])
        marks = add_library_emoji(updated, marks, mappings, category, max_emoji, avoid_ids=avoid_emoji_ids)
        after = len([mark for mark in marks if mark.type == "custom_emoji"])
        if after > before:
            applied.append(f"emoji_replacement:{after - before}")
    html_text = render_html(updated, marks)
    if html_text and "blockquote" in html_text and "preserve_quote" not in applied:
        applied.append("preserve_quote")
    return updated, html_text, marks_to_dicts(marks), emoji_spans(marks), applied
