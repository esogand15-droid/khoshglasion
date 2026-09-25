"""Import a Telegram custom-emoji pack into the library.

The bot never downloads a website catalog. It reads a public sticker-set name
from a t.me/addemoji link and asks Telegram for that set. Letter and digit
fallbacks are refused, because the replacer matches the fallback inside posts.
"""
from __future__ import annotations

import logging
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.formatting.richtext import is_lightning_line
from backend.app.formatting.richtext import _is_plain_rule
from backend.app.models.emoji import EmojiMapping

logger = logging.getLogger(__name__)

PACK_URL_RE = re.compile(
    r"(?:(?:https?://)?(?:t\.me|telegram\.me)/(?:addemoji|addstickers)/|tg://(?:addemoji|addstickers)\?set=)([A-Za-z0-9_]{1,128})",
    re.IGNORECASE,
)
BARE_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,128}$")
_KEYCAP_RE = re.compile(r"[0-9#*]\ufe0f?\u20e3")
_MODIFIERS = {"\ufe0f", "\ufe0e", "\u200d"}
MAX_PACKS = 3
MAX_STICKERS = 200


def parse_pack_names(text: str, *, allow_bare: bool = False) -> list[str]:
    found: list[str] = []
    for match in PACK_URL_RE.finditer(text or ""):
        name = match.group(1)
        if name not in found:
            found.append(name)
    if allow_bare and not found:
        for token in (text or "").replace("\n", " ").split():
            token = token.strip(".,)«»\"'")
            if token.startswith("/") or not BARE_NAME_RE.fullmatch(token) or token in found:
                continue
            found.append(token)
    return found[:MAX_PACKS]


def is_safe_fallback(value: str) -> bool:
    """True only when this fallback cannot replace letters or plain digits."""
    text = (value or "").strip()
    if not text or len(text) > 16:
        return False
    without_keycaps = _KEYCAP_RE.sub("", text)
    emoji_like = 0
    saw_keycap = without_keycaps != text
    for ch in without_keycaps:
        if ch in _MODIFIERS:
            continue
        category = unicodedata.category(ch)
        if category.startswith("L") or category.startswith("N"):
            return False
        if category.startswith(("P", "Z", "C")):
            return False
        if category == "Mn":
            continue
        if category == "Sk" and 0x1F3FB <= ord(ch) <= 0x1F3FF:
            continue
        if category == "So" or _is_emoji_char(ch):
            emoji_like += 1
            continue
        return False
    return emoji_like > 0 or saw_keycap


def _is_emoji_char(ch: str) -> bool:
    code = ord(ch)
    return (
        0x2190 <= code <= 0x21FF
        or 0x2300 <= code <= 0x23FF
        or 0x2460 <= code <= 0x24FF
        or 0x25A0 <= code <= 0x27BF
        or 0x2900 <= code <= 0x297F
        or 0x2B00 <= code <= 0x2BFF
        or 0x1F000 <= code <= 0x1FAFF
    )


def fallback_category(emoji: str) -> str | None:
    if is_lightning_line(emoji) or _is_plain_rule(emoji):
        return "divider"
    return None


def _field(obj, *keys):
    if isinstance(obj, dict):
        for key in keys:
            if obj.get(key) is not None:
                return obj.get(key)
        return None
    for key in keys:
        value = getattr(obj, key, None)
        if value is not None:
            return value
    return None


def stickers_of(sticker_set) -> tuple[str, str, list]:
    title = str(_field(sticker_set, "title") or "")
    kind = str(_field(sticker_set, "sticker_type", "stickerType") or "")
    stickers = list(_field(sticker_set, "stickers") or [])
    return title, kind, stickers[:MAX_STICKERS]


async def store_pack_stickers(db: AsyncSession, name: str, sticker_set) -> dict:
    title, kind, stickers = stickers_of(sticker_set)
    imported = 0
    duplicate = 0
    unsafe = 0
    custom = 0
    fresh: list[EmojiMapping] = []
    for sticker in stickers:
        emoji = str(_field(sticker, "emoji") or "")
        custom_id = str(_field(sticker, "custom_emoji_id", "customEmojiId") or "")
        if not custom_id.isdigit():
            continue
        custom += 1
        if not is_safe_fallback(emoji):
            unsafe += 1
            continue
        existing = (
            await db.execute(
                select(EmojiMapping).where(
                    EmojiMapping.unicode_emoji == emoji,
                    EmojiMapping.custom_emoji_id == custom_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.enabled = True
            if (existing.source or "") == "seed":
                existing.source = "pack"
            duplicate += 1
            continue
        added = EmojiMapping(
            unicode_emoji=emoji,
            custom_emoji_id=custom_id,
            enabled=True,
            category=fallback_category(emoji),
            priority=1,
            source="pack",
            label=(title or name)[:120],
        )
        db.add(added)
        fresh.append(added)
        imported += 1
    if custom == 0:
        error = "not_custom" if kind and kind != "custom_emoji" else "empty"
        return {
            "name": name,
            "title": title,
            "imported": 0,
            "duplicate": 0,
            "unsafe": 0,
            "error": error,
        }
    if fresh:
        await db.flush()
        from backend.app.services.emoji_order import append_ids

        await append_ids(db, [row.id for row in fresh])
    return {
        "name": name,
        "title": title or name,
        "imported": imported,
        "duplicate": duplicate,
        "unsafe": unsafe,
        "error": None,
    }


async def import_pack_names(db: AsyncSession, names: list[str], fetch) -> dict:
    packs = []
    for name in names[:MAX_PACKS]:
        try:
            sticker_set = await fetch(name)
        except PackFetchError as exc:
            packs.append({
                "name": name,
                "title": name,
                "imported": 0,
                "duplicate": 0,
                "unsafe": 0,
                "error": exc.code,
            })
            continue
        packs.append(await store_pack_stickers(db, name, sticker_set))
    result = {
        "packs": packs,
        "imported": sum(item["imported"] for item in packs),
        "duplicate": sum(item["duplicate"] for item in packs),
        "unsafe": sum(item["unsafe"] for item in packs),
    }
    result["message"] = format_pack_report(result)
    return result


class PackFetchError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def format_pack_report(result: dict) -> str:
    lines: list[str] = []
    for pack in result.get("packs") or []:
        title = pack.get("title") or pack.get("name")
        error = pack.get("error")
        if error == "not_found":
            lines.append(f"پک «{title}» در تلگرام پیدا نشد.")
            continue
        if error == "not_custom":
            lines.append(f"«{title}» بستهٔ استیکر معمولی است و ایموجی متحرک ندارد.")
            continue
        if error == "empty":
            lines.append(f"«{title}» ایموجی متحرک قابل استفاده نداشت.")
            continue
        if error == "bot_missing":
            lines.append("توکن ربات تنظیم نشده؛ پک خوانده نشد.")
            continue
        if error:
            lines.append(f"خواندن «{title}» از تلگرام انجام نشد.")
            continue
        lines.append(
            f"پک «{title}»: {pack['imported']} تازه، {pack['duplicate']} تکراری، {pack['unsafe']} رد شد."
        )
    if result.get("unsafe"):
        lines.append("حرف، عدد و فونت اضافه نشد تا داخل متن پست جایگزین نشود.")
    if not lines:
        lines.append("لینک پک شناخته نشد.")
    return "\n".join(lines)


def fetch_error_code(exc: Exception) -> str:
    text = str(exc)
    if "STICKERSET_INVALID" in text or "STICKERSET_NOT_FOUND" in text:
        return "not_found"
    return "fetch_failed"


async def fetch_sticker_set(name: str):
    from backend.app.telegram.bot import get_bot

    bot = get_bot()
    if bot is None:
        raise PackFetchError("bot_missing")
    try:
        return await bot.get_sticker_set(name)
    except Exception as exc:
        logger.warning("sticker set fetch failed: %s", type(exc).__name__)
        raise PackFetchError(fetch_error_code(exc)) from exc
