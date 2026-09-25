"""Keep draft photos in the database, not only on the container disk.

Railway throws the working directory away on every deploy. A path stored in
the draft is then a dead file, and the panel says the photo is gone. The
bytes live with the draft so the next open still has the picture.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.automation import DraftMedia

logger = logging.getLogger(__name__)


def read_image(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < 32 or len(data) > 8_000_000:
        return None
    if data.startswith(b"\xff\xd8") or data.startswith(b"\x89PNG") or (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        return data
    return None


async def load_photo(db: AsyncSession, draft_id: str, slot: int) -> bytes | None:
    try:
        async with db.begin_nested():
            row = (
                await db.execute(
                    select(DraftMedia).where(
                        DraftMedia.draft_id == draft_id,
                        DraftMedia.slot == int(slot),
                        DraftMedia.kind == "photo",
                    )
                )
            ).scalar_one_or_none()
    except Exception:
        logger.info("stored photo read skipped")
        return None
    data = bytes(row.data) if row is not None and row.data else None
    if data and len(data) >= 32:
        return data
    return None


async def remember_slot(db: AsyncSession, draft_id: str, slot: int, data: bytes) -> None:
    if not draft_id or not data or len(data) < 32:
        return
    row = (
        await db.execute(
            select(DraftMedia).where(
                DraftMedia.draft_id == draft_id,
                DraftMedia.slot == int(slot),
                DraftMedia.kind == "photo",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(DraftMedia(draft_id=draft_id, slot=int(slot), kind="photo", data=data))
    else:
        row.data = data


async def remember_paths(db: AsyncSession, draft_id: str, paths: list[str]) -> None:
    """Copy files that still exist. A missing table must not abort collection."""
    if not draft_id or not paths:
        return
    try:
        async with db.begin_nested():
            for slot, path in enumerate(paths):
                data = read_image(path)
                if data:
                    await remember_slot(db, draft_id, slot, data)
    except Exception:
        logger.info("draft photo bytes skipped")
