"""Style folder for konkour channels.

Each collect files a post into a style folder. The writer reads the resulting
card, not the source sentences. This is in-context style memory shared by
every provider in the model list. It does not upload posts for weight training
and it does not join a channel.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

FOLDERS: dict[str, dict[str, str]] = {
    "flash": {
        "label": "خبر فوری",
        "category": "news",
        "angle": "خبر کوتاه: یک تیتر و چند خط واقعیت",
        "rule": "یک تیتر کوتاه بنویس، بعد حداکثر چهار خط. هر خط یک واقعیت از همین منبع. مقدمهٔ «اگر تو» و مقالهٔ مشاوره ممنوع.",
        "skeleton": "تیتر: [ادعا یا نتیجه]\n[نهاد]: [یک واقعیت]\n[عدد یا تاریخ، فقط اگر در منبع هست]\n[یک خط جمع‌بندی، بدون توصیهٔ اضافه]",
    },
    "announce": {
        "label": "اطلاع‌رسانی",
        "category": "announcement",
        "angle": "اطلاعیه رسمی و کوتاه",
        "rule": "مثل اطلاعیه کانال کنکور: تیتر نتیجه، مهلت یا ظرفیت، بعد خط‌های کوتاه با همان عدد و اسم. توضیح اضافه نساز.",
        "skeleton": "تیتر: [موضوع اعلام]\n[مرجع]: [چه چیزی اعلام شد]\nمهلت یا عدد: [فقط اگر در منبع هست]\n[اثر عملی در یک خط]",
    },
    "fun": {
        "label": "فان",
        "category": "general",
        "angle": "فان و کوتاه، بدون نصیحت",
        "rule": "کوتاه و شوخ بنویس. جوک را به درس اخلاق یا برنامهٔ مطالعاتی تبدیل نکن. واقعیت تازه نساز.",
        "skeleton": "[یک خط شوخ و مستقیم]\n[اگر منبع واقعیت دارد، یک خط]\n[سؤال کوتاه، اختیاری]",
    },
    "guide": {
        "label": "راهنما و مقایسه",
        "category": "lesson",
        "angle": "بلوک‌های کوتاه برچسب‌دار",
        "rule": "بلوک‌های کوتاه با برچسب بنویس، مثل مقایسه یا هزینه. هر بلوک یکی دو خط. انشا ننویس.",
        "skeleton": "[عنوان مقایسه یا هزینه]\n[برچسب]: [یک واقعیت]\n[برچسب]: [یک واقعیت]\n[جمع‌بندی یک خط]",
    },
    "alert": {
        "label": "اصلاح و هشدار",
        "category": "news",
        "angle": "اصلاح دقیق، بدون حاشیه",
        "rule": "اول بگو چه چیزی اصلاح یا رد شد، بعد فقط واقعیت منبع. شایعه را خبر قطعی ننویس.",
        "skeleton": "تیتر: [چه چیزی اصلاح شد]\nآنچه درست است: [واقعیت منبع]\nآنچه نباید قطعی گفته شود: [اگر منبع رد کرده]",
    },
    "consult": {
        "label": "مشاوره کوتاه",
        "category": "consulting",
        "angle": "مشاوره کوتاه، فقط اگر منبع خودش توصیه است",
        "rule": "فقط اگر منبع خودش توصیه است دو پاراگراف کوتاه بنویس. خبر را به توصیه تبدیل نکن.",
        "skeleton": "[مسئله در یک خط]\n[توصیهٔ کوتاه، فقط اگر در منبع هست]\n[یک اقدام مشخص]",
    },
}

BASE_CARD = (
    "سبک کانال‌های کنکور، از روی پست‌های واقعی‌شان:\n"
    "خبر و اطلاعیه یک تیتر و چند خط واقعیت است، نه سه پاراگراف مشاوره.\n"
    "فان کوتاه و شوخ است و نباید نصیحت شود.\n"
    "راهنما بلوک برچسب‌دار است، مثل هزینه یا مقایسه.\n"
    "جملهٔ هیچ نمونه‌ای را کپی نکن. عدد و اسم را فقط از پیام همین نوبت بردار."
)

_ALERT = ("تکذیب", "اصلاح شد", "اصلاحیه", "برگشت", "شایعه", "واقعیت ندارد")
_GUIDE = ("هزینه", "تومان", "تفاوت", "مقایسه", "کدام داوطلب")
_ANNOUNCE = (
    "ثبت‌نام",
    "ثبت نام",
    "اعلام نتایج",
    "نتایج نهایی",
    "بخشنامه",
    "ظرفیت پذیرش",
    "تاثیر معدل",
    "سوابق تحصیلی",
    "مهلت",
    "حذف برخی رشته",
)
_FUN = ("جوک", "میم", "بخند", "شیبا", "😂", "🤣")
_CONSULT = ("بهتر است", "برنامه مطالعاتی", "برنامهٔ مطالعاتی", "اگر شما", "اگر تو")
_OFFICIAL = (
    "سازمان",
    "وزارت",
    "سنجش",
    "کنکور",
    "دانشگاه",
    "آموزش و پرورش",
    "ثبت‌نام",
    "ثبت نام",
    "اعلام",
    "ظرفیت",
    "هواشناسی",
)
_CAP = 40


def _fold(text: str) -> str:
    return (
        (text or "")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("ة", "ه")
    )


def classify_style(text: str) -> str:
    raw = _fold(text)
    official = any(word in raw for word in _OFFICIAL)
    if any(word in raw for word in _ALERT):
        return "alert"
    if len(raw) >= 40 and any(word in raw for word in _GUIDE):
        return "guide"
    if any(word in raw for word in _ANNOUNCE):
        return "announce"
    if any(word in raw for word in _FUN):
        return "fun"
    if not official and any(word in raw for word in _CONSULT):
        return "consult"
    if official or "فوری" in raw or "اخبار" in raw:
        return "flash"
    if len(raw) < 180:
        return "fun"
    return "flash"


def folder_label(style: str) -> str:
    return FOLDERS.get(style, FOLDERS["flash"])["label"]


def folder_category(style: str) -> str:
    return FOLDERS.get(style, FOLDERS["flash"])["category"]


def angle_label(style: str) -> str:
    return FOLDERS.get(style, FOLDERS["flash"])["angle"]


def writer_context(style: str, card: str | None = None) -> str:
    item = FOLDERS.get(style) or FOLDERS["flash"]
    return (
        f"سبک این پیام: {item['label']}\n"
        f"قانون این سبک: {item['rule']}\n"
        f"ساختار، کپی نکن:\n{item['skeleton']}\n"
        f"{(card or base_card()).strip()}"
    )


def base_card() -> str:
    return BASE_CARD


def render_card(rows: list) -> str:
    lines = [BASE_CARD, ""]
    if not rows:
        lines.append("هنوز نمونه‌ای جمع نشده. با جمع‌آوری، پوشه‌ها پر می‌شوند و طول خط‌ها دقیق‌تر می‌شود.")
        return "\n".join(lines)
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.folder, []).append(row)
    lines.append(f"نمونه‌های ذخیره‌شده: {len(rows)}")
    for key, item in FOLDERS.items():
        group = grouped.get(key) or []
        if not group:
            continue
        chars = sorted(int(row.chars or 0) for row in group)
        line_counts = sorted(int(row.lines or 0) for row in group)
        lines.append(
            f"- {item['label']}: {len(group)} نمونه، حدود {chars[len(chars) // 2]} حرف و {line_counts[len(line_counts) // 2]} خط."
        )
    dominant = max(grouped, key=lambda key: len(grouped[key]))
    lines.append(f"سبک غالب منابع: {folder_label(dominant)}. خبر را به مقالهٔ مشاوره تبدیل نکن.")
    return "\n".join(lines)


def _root() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "finetune"


def _file_id(source_key: str) -> str:
    return hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:16]


def _write_sample(folder: str, source_key: str, payload: dict) -> None:
    try:
        directory = _root() / folder
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{_file_id(source_key)}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.info("finetune folder write skipped: %s", type(exc).__name__)


def _write_card(card: str) -> None:
    try:
        root = _root()
        root.mkdir(parents=True, exist_ok=True)
        (root / "card.txt").write_text(card, encoding="utf-8")
    except Exception as exc:
        logger.info("finetune card write skipped: %s", type(exc).__name__)


def _unlink(folder: str, source_key: str) -> None:
    try:
        path = _root() / folder / f"{_file_id(source_key)}.json"
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.info("finetune folder cleanup skipped: %s", type(exc).__name__)


async def load_rows(db: AsyncSession) -> list:
    from backend.app.models.automation import StyleSample

    return list((await db.execute(select(StyleSample).order_by(StyleSample.created_at.desc()))).scalars().all())


async def load_card(db: AsyncSession) -> str:
    card = render_card(await load_rows(db))
    _write_card(card)
    return card


async def remember_sample(db: AsyncSession, *, source_key: str, source_label: str | None, text: str) -> int:
    from backend.app.content.pipeline import AD_WORDS
    from backend.app.models.automation import StyleSample

    raw = (text or "").strip()
    if len(raw) < 40 or any(word in raw for word in AD_WORDS):
        return 0
    key = (source_key or "").strip()[:160]
    if not key:
        return 0
    existing = (await db.execute(select(StyleSample.id).where(StyleSample.source_key == key))).first()
    if existing:
        return 0
    folder = classify_style(raw)
    if folder not in FOLDERS:
        folder = "flash"
    excerpt = raw[:360]
    row = StyleSample(
        folder=folder,
        source_key=key,
        source_label=(source_label or "")[:256] or None,
        excerpt=excerpt,
        chars=len(raw),
        lines=max(1, len([line for line in raw.splitlines() if line.strip()])),
    )
    db.add(row)
    await db.flush()
    _write_sample(folder, key, {
        "folder": folder,
        "label": row.source_label,
        "excerpt": excerpt,
        "chars": row.chars,
        "lines": row.lines,
    })
    older = (
        await db.execute(
            select(StyleSample).where(StyleSample.folder == folder).order_by(StyleSample.created_at.desc())
        )
    ).scalars().all()
    for stale in older[_CAP:]:
        _unlink(stale.folder, stale.source_key)
        await db.delete(stale)
    return 1


async def snapshot(db: AsyncSession) -> dict:
    rows = await load_rows(db)
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.folder, []).append(row)
    folders = []
    for key, item in FOLDERS.items():
        group = grouped.get(key) or []
        folders.append({
            "id": key,
            "label": item["label"],
            "count": len(group),
            "samples": [
                {
                    "label": row.source_label,
                    "excerpt": row.excerpt,
                    "chars": row.chars,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in group[:6]
            ],
        })
    return {
        "total": len(rows),
        "card": render_card(rows),
        "folders": folders,
    }


def keep_fun(text: str, judgment: dict, style: str) -> bool:
    if style != "fun" or judgment.get("value") != "LOW_VALUE":
        return False
    if "too_short" in (judgment.get("reasons") or []):
        return False
    raw = text or ""
    if "استیکر" in raw or "فقط فوروارد" in raw:
        return False
    return len(raw.strip()) >= 80
