"""What may become a post, and where each part sits.

Ads from other channels are refused before a model is called. A short notice
is rearranged, not summarized. A photo stays a photo: the writer never invents
an emoji id, and the library still places those at publish time.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

AD_CUES = (
    "تبلیغ",
    "اسپانسر",
    "همکاری تبلیغاتی",
    "کد تخفیف",
    "فالو کن",
    "دایرکت",
    "لینک خرید",
    "برای خرید",
    "سفارش دهید",
    "زرین‌پال",
    "زرین پال",
    "ظرفیت محدود",
    "تخفیف ویژه",
    "قیمت ویژه",
    "لینک بیو",
    "این پست تبلیغ",
    "پیام بده",
    "مشاوره رایگان",
)
OFFICIAL = ("کنکور", "سازمان سنجش", "مهلت", "بخشنامه", "اعلام نتایج", "وزارت", "دانشگاه")
SALES = ("خرید", "سفارش", "تخفیف", "پرداخت", "دایرکت", "ثبت‌نام کن", "ثبت نام کن")


def is_advertisement(text: str) -> bool:
    raw = text or ""
    if any(word in raw for word in ("کد تخفیف", "اسپانسر", "همکاری تبلیغاتی", "این پست تبلیغ", "لینک خرید", "زرین‌پال", "زرین پال")):
        return True
    official = any(word in raw for word in OFFICIAL)
    if official:
        return False
    if any(word in raw for word in AD_CUES) and any(word in raw for word in SALES):
        return True
    if "تومان" in raw and any(word in raw for word in ("تخفیف", "خرید", "سفارش", "ظرفیت محدود")):
        return True
    return False


def rewrite_plan(text: str) -> str:
    """Short complete notes stay complete. Only a long source is shortened."""
    raw = (text or "").strip()
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(raw) <= 720 and len(lines) <= 14:
        return "preserve"
    return "summarize"


def layout_for(category: str | None, style: str | None, plan: str) -> str:
    if (category or "") in {"news", "announcement", "registration"}:
        return "title"
    if style == "fun":
        return "scatter"
    if style in {"guide", "consult"} or category in {"lesson", "planning", "consulting"}:
        return "list"
    if plan == "summarize":
        return "list"
    return "title"


def copied_whole(source: str, draft: str) -> bool:
    left = re.sub(r"\s+", "", source or "")
    right = re.sub(r"\s+", "", draft or "")
    if len(left) < 80 or len(right) < 80:
        return False
    return left in right or right in left


def media_root() -> Path:
    raw = os.environ.get("AUTOPOST_MEDIA_DIR") or "data/autopost-media"
    root = Path(raw)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def save_source_photo(source_key: str, data: bytes) -> str | None:
    if not data or len(data) < 32 or len(data) > 8_000_000:
        return None
    if not (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG") or data.startswith(b"RIFF")):
        return None
    name = hashlib.sha256((source_key or "").encode()).hexdigest()[:24] + ".img"
    path = media_root() / name
    path.write_bytes(data)
    return str(path)


def photo_of(raw: str | None) -> str | None:
    import json

    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    path = data.get("photo_path")
    found = safe_photo_path(path if isinstance(path, str) else None)
    return str(found) if found else None


def safe_photo_path(stored: str | None) -> Path | None:
    if not stored:
        return None
    root = media_root()
    name = Path(stored).name
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return None
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path


def image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"RIFF"):
        return "image/webp"
    return "image/jpeg"
