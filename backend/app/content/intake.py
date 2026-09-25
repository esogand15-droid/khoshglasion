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


def image_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def save_source_photo(source_key: str, data: bytes) -> str | None:
    if not data or len(data) < 32 or len(data) > 8_000_000:
        return None
    if not (data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG") or data.startswith(b"RIFF")):
        return None
    name = hashlib.sha256((source_key or "").encode()).hexdigest()[:24] + image_suffix(data)
    path = media_root() / name
    path.write_bytes(data)
    return str(path)


def save_source_video(source_key: str, data: bytes) -> str | None:
    if not data or len(data) < 32 or len(data) > 20_000_000:
        return None
    if data[4:8] == b"ftyp":
        suffix = ".mp4"
    elif data.startswith(b"\x1a\x45\xdf\xa3"):
        suffix = ".webm"
    else:
        return None
    name = hashlib.sha256((source_key or "").encode()).hexdigest()[:24] + suffix
    path = media_root() / name
    path.write_bytes(data)
    return str(path)


def _analysis(raw: str | None) -> dict:
    import json

    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def photo_paths_of(raw: str | None) -> list[str]:
    data = _analysis(raw)
    found: list[str] = []
    for item in data.get("photo_paths") or []:
        path = safe_photo_path(item if isinstance(item, str) else None)
        if path and str(path) not in found:
            found.append(str(path))
    single = safe_photo_path(data.get("photo_path") if isinstance(data.get("photo_path"), str) else None)
    if single and str(single) not in found:
        found.insert(0, str(single))
    return found


def video_of(raw: str | None) -> str | None:
    path = _analysis(raw).get("video_path")
    found = safe_media_path(path if isinstance(path, str) else None)
    return str(found) if found else None


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


_PHOTO_NAME = re.compile(r"^[A-Za-z0-9_-]{8,80}\.(?:jpg|jpeg|png|webp|img)$")
_MEDIA_NAME = re.compile(r"^[A-Za-z0-9_-]{8,80}\.(?:jpg|jpeg|png|webp|img|mp4|webm|mov)$")


def safe_media_path(stored: str | None) -> Path | None:
    """A saved photo or video. The name must stay inside the media directory."""
    if not stored:
        return None
    name = Path(stored).name
    if not _MEDIA_NAME.fullmatch(name):
        return None
    root = media_root()
    current = (root / name).resolve()
    try:
        current.relative_to(root)
    except ValueError:
        return None
    if current.is_file():
        return current
    raw = Path(stored)
    if raw.is_file() and raw.name == name:
        return raw
    return None


def safe_photo_path(stored: str | None) -> Path | None:
    """Find a saved source photo. A moved working directory must not hide it."""
    if not stored:
        return None
    name = Path(stored).name
    if not _PHOTO_NAME.fullmatch(name):
        return None
    root = media_root()
    current = (root / name).resolve()
    try:
        current.relative_to(root)
    except ValueError:
        return None
    if current.is_file():
        return current
    raw = Path(stored)
    if not raw.is_absolute():
        return None
    try:
        previous = raw.resolve()
    except OSError:
        return None
    owned = previous.parent == root or previous.parent.name in {root.name, "autopost-media"}
    if not previous.is_file() or previous.name != name or not owned:
        return None
    try:
        current.write_bytes(previous.read_bytes())
    except OSError:
        return previous
    return current if current.is_file() else previous


def image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"RIFF"):
        return "image/webp"
    return "image/jpeg"


def _webp_to_jpeg(data: bytes) -> bytes | None:
    try:
        from io import BytesIO
        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(BytesIO(data)).convert("RGB")
        out = BytesIO()
        image.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return None


def photo_bytes_for_telegram(path: Path) -> tuple[bytes, str]:
    """Bytes plus a .jpg/.png name. Telegram shows an unknown extension as a file."""
    data = path.read_bytes()
    if data.startswith(b"\x89PNG"):
        return data, "photo.png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        converted = _webp_to_jpeg(data)
        if converted:
            return converted, "photo.jpg"
    return data, "photo.jpg"
