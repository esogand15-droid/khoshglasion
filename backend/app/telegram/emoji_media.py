"""Preview a library custom emoji through the official Bot API.

Telegram methods used, and only these: getCustomEmojiStickers, getFile, then
the bot file download. The token never leaves the server. Standard unicode
emoji have no animated file in the Bot API; the sticker's own ``emoji`` field
is the default character Telegram attaches to that custom emoji.
"""
from __future__ import annotations

import gzip
import json
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_IDS = 200
MAX_REQUEST = 1000
MAX_BYTES = 1_000_000
META_TTL = 30 * 60
FILE_TTL = 2 * 60 * 60
NEGATIVE_TTL = 10 * 60
MAX_CACHED_FILES = 240
FAKE_PREFIX = "53683241"


@dataclass
class CachedSticker:
    public: dict
    file_id: str
    expires: float


_meta: dict[str, CachedSticker] = {}
_missing: dict[str, float] = {}
_files: dict[str, tuple[float, bytes, str]] = {}


def clean_ids(raw_ids: list) -> list[str]:
    found: list[str] = []
    for raw in raw_ids or []:
        item = str(raw or "").strip()
        if not item.isdigit() or not 1 <= len(item) <= 64 or item in found:
            continue
        found.append(item)
        if len(found) >= MAX_REQUEST:
            break
    return found


def public_sticker(sticker) -> dict:
    animated = bool(getattr(sticker, "is_animated", False))
    video = bool(getattr(sticker, "is_video", False))
    if video:
        fmt = "webm"
    elif animated:
        fmt = "lottie"
    else:
        fmt = "image"
    return {
        "custom_emoji_id": str(getattr(sticker, "custom_emoji_id", "") or ""),
        "emoji": str(getattr(sticker, "emoji", "") or ""),
        "set_name": str(getattr(sticker, "set_name", "") or ""),
        "is_animated": animated,
        "is_video": video,
        "format": fmt,
        "width": int(getattr(sticker, "width", 0) or 0),
        "height": int(getattr(sticker, "height", 0) or 0),
    }


def image_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return "application/octet-stream"


def decode_tgs(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if len(data) > MAX_BYTES:
        raise ValueError("too_large")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError("not_lottie")
    return data


def _remember_file(custom_id: str, data: bytes, content_type: str) -> None:
    now = time.monotonic()
    expired = [key for key, (expires, _, _) in _files.items() if expires <= now]
    for key in expired:
        _files.pop(key, None)
    while len(_files) >= MAX_CACHED_FILES:
        oldest = min(_files, key=lambda key: _files[key][0])
        _files.pop(oldest, None)
    _files[custom_id] = (now + FILE_TTL, data, content_type)


async def describe_custom_emojis(bot, ids: list[str]) -> tuple[list[dict], list[str]]:
    """Return public sticker facts. file_id stays in the server cache."""
    now = time.monotonic()
    wanted: list[str] = []
    items: list[dict] = []
    missing: list[str] = []
    for custom_id in ids:
        if custom_id.startswith(FAKE_PREFIX):
            missing.append(custom_id)
            continue
        cached = _meta.get(custom_id)
        if cached and cached.expires > now:
            items.append(dict(cached.public))
            continue
        if _missing.get(custom_id, 0) > now:
            missing.append(custom_id)
            continue
        wanted.append(custom_id)
    if wanted and bot is not None:
        found: set[str] = set()
        for start in range(0, len(wanted), MAX_IDS):
            chunk = wanted[start:start + MAX_IDS]
            try:
                stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=chunk)
            except Exception as exc:
                logger.warning("custom emoji lookup failed: %s", type(exc).__name__)
                raise
            for sticker in stickers or []:
                public = public_sticker(sticker)
                custom_id = public["custom_emoji_id"]
                file_id = str(getattr(sticker, "file_id", "") or "")
                if not custom_id.isdigit() or not file_id:
                    continue
                _meta[custom_id] = CachedSticker(public=public, file_id=file_id, expires=now + META_TTL)
                _missing.pop(custom_id, None)
                items.append(dict(public))
                found.add(custom_id)
        for custom_id in wanted:
            if custom_id not in found:
                _missing[custom_id] = now + NEGATIVE_TTL
                missing.append(custom_id)
    elif wanted:
        missing.extend(wanted)
    return items, missing


async def load_custom_emoji_file(bot, custom_id: str) -> tuple[bytes, str]:
    cached = _files.get(custom_id)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1], cached[2]
    meta = _meta.get(custom_id)
    if meta is None or meta.expires <= now:
        await describe_custom_emojis(bot, [custom_id])
        meta = _meta.get(custom_id)
    if meta is None or not meta.file_id:
        raise LookupError("missing")
    telegram_file = await bot.get_file(meta.file_id)
    file_path = str(getattr(telegram_file, "file_path", "") or "")
    if not file_path or ".." in file_path.replace("\\", "/"):
        raise LookupError("unavailable")
    buffer = await bot.download_file(file_path)
    if buffer is None:
        raise LookupError("unavailable")
    data = buffer.read()
    if not data or len(data) > MAX_BYTES:
        raise LookupError("unavailable")
    if meta.public.get("format") == "lottie":
        try:
            data = decode_tgs(data)
        except Exception as exc:
            logger.warning("tgs decode failed: %s", type(exc).__name__)
            raise LookupError("unavailable") from exc
        content_type = "application/json"
    elif meta.public.get("format") == "webm":
        content_type = "video/webm"
    else:
        content_type = image_type(data)
        if content_type == "application/octet-stream":
            raise LookupError("unavailable")
    _remember_file(custom_id, data, content_type)
    return data, content_type
