import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.models.emoji import EmojiMapping
from backend.app.schemas.emoji import EmojiCreate, EmojiUpdate
from backend.app.security.deps import assert_editor, get_current_admin
from backend.app.services.audit import write_audit
from backend.app.formatting.spectrum import SPECTRA, guess_spectrum, parse_ai_spectra, spectrum_of
from backend.app.services.ai import complete_text
from backend.app.core.runtime import load_runtime
from backend.app.telegram.bot import get_bot
from backend.app.telegram.emoji_media import clean_ids, describe_custom_emojis, load_custom_emoji_file
from backend.app.telegram.emoji_pack import fetch_sticker_set, import_pack_names, is_safe_fallback, parse_pack_names

router = APIRouter(prefix="/api/emojis", tags=["emojis"])


def _stamp_spectrum(row: EmojiMapping, spectrum: str, source: str) -> None:
    row.category = spectrum
    row.contexts = json.dumps([spectrum], ensure_ascii=False)
    row.source = source


def _needs_spectrum(row: EmojiMapping) -> bool:
    return not (row.category or "").strip()


async def _classify_batch(runtime, batch: list[EmojiMapping]) -> tuple[dict[int, tuple[str, str]], str]:
    prompt_lines = [f"{index}={row.unicode_emoji or row.label or '?'}" for index, row in enumerate(batch, 1)]
    answer = await complete_text(
        runtime,
        [
            {
                "role": "system",
                "content": (
                    "هر ایموجی را با حال‌وهوایش در یکی از این طیف‌ها بگذار: "
                    "news خبر، announcement اطلاعیه، fun فان، guide راهنما، alert هشدار، consulting مشاوره، general عمومی. "
                    "فقط خط‌هایی به شکل شماره=کلید برگردان. توضیح ننویس."
                ),
            },
            {"role": "user", "content": "\n".join(prompt_lines)},
        ],
    )
    parsed = parse_ai_spectra(answer or "")
    assigned: dict[int, tuple[str, str]] = {}
    for index, row in enumerate(batch, 1):
        glyph = (row.unicode_emoji or "").strip()
        key = parsed.get(str(index)) or parsed.get(glyph)
        if key in SPECTRA:
            assigned[index] = (key, "ai")
            continue
        guessed = guess_spectrum(glyph)
        if guessed:
            assigned[index] = (guessed, "guess")
    return assigned, "ai" if parsed else "guess"


async def _classify_rows(db: AsyncSession, rows: list[EmojiMapping], *, force: bool, after_id: str = "") -> dict:
    pending = list(rows) if force else [row for row in rows if _needs_spectrum(row)]
    skipped = len(rows) - len(pending)
    if after_id and not force:
        pending = [row for row in pending if (row.id or "") > after_id]
    if not pending:
        return {"changed": 0, "skipped": skipped, "by": "none", "left": 0, "after_id": after_id}
    runtime = await load_runtime(db)
    changed = 0
    by = "none"
    cursor = 0
    rounds = 0
    while cursor < len(pending) and rounds < 4:
        batch = pending[cursor:cursor + 30]
        rounds += 1
        assigned, batch_by = await _classify_batch(runtime, batch)
        if batch_by == "ai" or by == "none":
            by = batch_by
        for index, row in enumerate(batch, 1):
            item = assigned.get(index)
            if not item:
                continue
            key, source = item
            _stamp_spectrum(row, key, source)
            changed += 1
        cursor += len(batch)
    last_id = pending[cursor - 1].id if cursor else after_id
    open_left = sum(1 for row in rows if _needs_spectrum(row))
    return {"changed": changed, "skipped": skipped, "by": by, "left": max(0, len(pending) - cursor), "open": open_left, "after_id": last_id or ""}


def dump_emoji(row: EmojiMapping) -> dict:
    return {
        "id": row.id,
        "unicode_emoji": row.unicode_emoji,
        "custom_emoji_id": row.custom_emoji_id,
        "enabled": row.enabled,
        "category": row.category,
        "contexts": row.contexts,
        "priority": row.priority,
        "usage_count": row.usage_count,
        "label": row.label,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/export")
async def export_emojis(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    rows = (await db.execute(select(EmojiMapping))).scalars().all()
    return [dump_emoji(row) for row in rows]


@router.post("/import")
async def import_emojis(payload: list[dict], db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    if len(payload) > 2000:
        raise HTTPException(status_code=400, detail="هر بار حداکثر ۲۰۰۰ ایموجی")
    imported = 0
    for item in payload:
        emoji = item.get("unicode_emoji")
        custom_id = str(item.get("custom_emoji_id") or "")
        if not emoji or not custom_id.isdigit():
            continue
        existing = (
            await db.execute(
                select(EmojiMapping).where(EmojiMapping.unicode_emoji == emoji, EmojiMapping.custom_emoji_id == custom_id)
            )
        ).scalar_one_or_none()
        contexts = item.get("contexts")
        if isinstance(contexts, list):
            contexts = json.dumps(contexts, ensure_ascii=False)
        if existing:
            existing.enabled = item.get("enabled", existing.enabled)
            existing.category = item.get("category", existing.category)
            existing.priority = item.get("priority", existing.priority)
            existing.label = item.get("label", existing.label)
            if contexts is not None:
                existing.contexts = contexts
            continue
        db.add(EmojiMapping(
            unicode_emoji=emoji,
            custom_emoji_id=custom_id,
            enabled=item.get("enabled", True),
            category=item.get("category"),
            contexts=contexts,
            priority=item.get("priority", 50),
            label=item.get("label"),
            source="import",
        ))
        imported += 1
    await db.flush()
    return {"imported": imported}


@router.post("/import-pack")
async def import_pack(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    raw = str(payload.get("url") or payload.get("link") or payload.get("name") or "").strip()
    names = parse_pack_names(raw, allow_bare=True)
    if not names:
        raise HTTPException(status_code=400, detail="لینک پک معتبر نیست. نمونه: https://t.me/addemoji/Name")
    if get_bot() is None:
        raise HTTPException(status_code=400, detail="توکن ربات تنظیم نشده")
    result = await import_pack_names(db, names, fetch_sticker_set)
    await write_audit(db, admin=admin, action="import_pack", resource="emoji", resource_id=names[0], ip_address=None)
    return result


@router.post("/previews")
async def preview_emojis(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    ids = clean_ids(payload.get("custom_emoji_ids") or payload.get("ids") or [])
    if not ids:
        return {"items": [], "missing": []}
    known = set(
        (
            await db.execute(select(EmojiMapping.custom_emoji_id).where(EmojiMapping.custom_emoji_id.in_(ids)))
        ).scalars().all()
    )
    wanted = [item for item in ids if item in known]
    missing = [item for item in ids if item not in known]
    bot = get_bot()
    if not wanted:
        return {"items": [], "missing": missing}
    if bot is None:
        return {"items": [], "missing": missing + wanted, "error": "توکن ربات تنظیم نشده"}
    try:
        items, not_found = await describe_custom_emojis(bot, wanted)
    except Exception:
        raise HTTPException(status_code=502, detail="خواندن ایموجی از تلگرام انجام نشد")
    return {"items": items, "missing": missing + not_found}


@router.get("/media/{custom_emoji_id}")
async def emoji_media(custom_emoji_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    custom_id = str(custom_emoji_id or "").strip()
    if not custom_id.isdigit() or len(custom_id) > 64:
        raise HTTPException(status_code=404, detail="ایموجی پیدا نشد")
    owned = (
        await db.execute(select(EmojiMapping.id).where(EmojiMapping.custom_emoji_id == custom_id).limit(1))
    ).scalar_one_or_none()
    if not owned:
        raise HTTPException(status_code=404, detail="این شناسه در کتابخانه نیست")
    bot = get_bot()
    if bot is None:
        raise HTTPException(status_code=400, detail="توکن ربات تنظیم نشده")
    try:
        data, content_type = await load_custom_emoji_file(bot, custom_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="تلگرام فایل این ایموجی را نداد")
    except Exception:
        raise HTTPException(status_code=502, detail="خواندن فایل ایموجی از تلگرام انجام نشد")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/{emoji_id}/telegram-fallback")
async def apply_telegram_fallback(emoji_id: str, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(EmojiMapping).where(EmojiMapping.id == emoji_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="ایموجی پیدا نشد")
    bot = get_bot()
    if bot is None:
        raise HTTPException(status_code=400, detail="توکن ربات تنظیم نشده")
    try:
        items, _missing = await describe_custom_emojis(bot, [row.custom_emoji_id])
    except Exception:
        raise HTTPException(status_code=502, detail="خواندن ایموجی از تلگرام انجام نشد")
    emoji = items[0]["emoji"] if items else ""
    if not is_safe_fallback(emoji):
        raise HTTPException(status_code=400, detail="تلگرام برای این استیکر ایموجی معمولی قابل استفاده برنگرداند")
    row.unicode_emoji = emoji
    await write_audit(
        db,
        admin=admin,
        action="telegram_fallback",
        resource="emoji",
        resource_id=row.id,
        ip_address=request.client.host if request.client else None,
    )
    return dump_emoji(row)


@router.post("/bulk")
async def bulk_emojis(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    ids = []
    for raw in payload.get("ids") or []:
        item = str(raw or "").strip()
        if item and item not in ids:
            ids.append(item)
        if len(ids) >= 500:
            break
    if not ids:
        raise HTTPException(status_code=400, detail="چیزی انتخاب نشده")
    action = str(payload.get("action") or "").strip()
    rows = (await db.execute(select(EmojiMapping).where(EmojiMapping.id.in_(ids)))).scalars().all()
    if action == "delete":
        for row in rows:
            await db.delete(row)
    elif action == "enable":
        for row in rows:
            row.enabled = True
    elif action == "disable":
        for row in rows:
            row.enabled = False
    elif action == "category":
        category = str(payload.get("category") or "").strip()[:64] or None
        spectrum = spectrum_of(category) if category else None
        for row in rows:
            if spectrum:
                _stamp_spectrum(row, spectrum, "manual")
            else:
                row.category = None
                row.source = "manual"
    elif action == "priority":
        try:
            priority = int(payload.get("priority"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="اولویت عدد نیست")
        if not 0 <= priority <= 1000:
            raise HTTPException(status_code=400, detail="اولویت باید بین ۰ و ۱۰۰۰ باشد")
        for row in rows:
            row.priority = priority
    else:
        raise HTTPException(status_code=400, detail="این کار گروهی شناخته نشد")
    return {"ok": True, "count": len(rows)}


@router.post("/classify")
async def classify_emojis(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    ids = [str(item).strip() for item in (payload.get("ids") or []) if str(item).strip()][:80]
    force = bool(payload.get("force")) and bool(ids)
    after_id = "" if force else str(payload.get("after_id") or "")
    query = select(EmojiMapping).order_by(EmojiMapping.id)
    if force:
        query = query.where(EmojiMapping.id.in_(ids))
    rows = (await db.execute(query)).scalars().all()
    result = await _classify_rows(db, list(rows), force=force, after_id=after_id)
    return {"ok": True, **result}


@router.post("/validate")
async def validate_emojis(payload: dict, admin=Depends(get_current_admin)):
    ids = [str(item).strip() for item in (payload.get("custom_emoji_ids") or payload.get("ids") or [])]
    ids = [item for item in ids if item.isdigit()][:50]
    if not ids:
        return {"found": [], "valid": [], "invalid": []}
    bot = get_bot()
    if not bot:
        return {"found": [], "valid": [], "invalid": ids, "note": "توکن ربات تنظیم نشده"}
    try:
        stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=ids)
        found = {str(getattr(sticker, "custom_emoji_id", "")) for sticker in (stickers or [])}
        found.discard("")
        return {"found": sorted(found), "valid": sorted(found), "invalid": [item for item in ids if item not in found]}
    except Exception as exc:
        return {"found": [], "valid": [], "invalid": ids, "error": str(exc)}


@router.post("/cleanup-fake")
async def cleanup_fake(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    rows = (await db.execute(select(EmojiMapping).where(EmojiMapping.custom_emoji_id.like("53683241%")))).scalars().all()
    for row in rows:
        await db.delete(row)
    await db.flush()
    return {"removed": len(rows)}


@router.get("")
async def list_emojis(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    rows = (await db.execute(select(EmojiMapping).order_by(EmojiMapping.priority.desc(), EmojiMapping.usage_count.desc()))).scalars().all()
    return [dump_emoji(row) for row in rows]


@router.post("")
async def create_emoji(payload: EmojiCreate, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    if not str(payload.custom_emoji_id).isdigit():
        raise HTTPException(status_code=400, detail="custom_emoji_id باید عدد باشد")
    row = EmojiMapping(
        unicode_emoji=payload.unicode_emoji,
        custom_emoji_id=payload.custom_emoji_id.strip(),
        enabled=payload.enabled,
        category=spectrum_of(payload.category) if payload.category else None,
        contexts=json.dumps([spectrum_of(payload.category)], ensure_ascii=False) if payload.category else (json.dumps(payload.contexts, ensure_ascii=False) if payload.contexts else None),
        priority=payload.priority,
        source="manual" if payload.category else "panel",
    )
    db.add(row)
    await db.flush()
    await write_audit(db, admin=admin, action="create", resource="emoji", resource_id=row.id, ip_address=request.client.host if request.client else None)
    return dump_emoji(row)


@router.patch("/{emoji_id}")
async def update_emoji(emoji_id: str, payload: EmojiUpdate, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(EmojiMapping).where(EmojiMapping.id == emoji_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="ایموجی پیدا نشد")
    data = payload.model_dump(exclude_unset=True)
    if "priority" in data:
        priority = data["priority"]
        if priority is None or not isinstance(priority, int) or not 0 <= priority <= 1000:
            raise HTTPException(status_code=400, detail="اولویت باید بین ۰ و ۱۰۰۰ باشد")
    if "category" in data:
        chosen = data.pop("category")
        if chosen:
            _stamp_spectrum(row, spectrum_of(str(chosen)), "manual")
        else:
            row.category = None
            row.contexts = None
            row.source = "manual"
        data.pop("contexts", None)
        data.pop("source", None)
    elif "contexts" in data and data["contexts"] is not None:
        data["contexts"] = json.dumps(data["contexts"], ensure_ascii=False)
    for key, value in data.items():
        setattr(row, key, value)
    return dump_emoji(row)


@router.delete("/{emoji_id}")
async def delete_emoji(emoji_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(EmojiMapping).where(EmojiMapping.id == emoji_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="ایموجی پیدا نشد")
    await db.delete(row)
    return {"ok": True}
