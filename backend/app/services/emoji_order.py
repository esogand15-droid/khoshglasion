"""Queue order for the premium emoji library.

The panel used to ask for a number. The number is still the column the poster,
the channel editor and the divider picker already sort on: a higher value is
earlier in that spectrum's queue. The operator never types it. Dragging a card
rewrites the queue, and a newly classified emoji waits at the end.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.formatting.spectrum import SPECTRA, spectrum_of
from backend.app.models.emoji import EmojiMapping

ROLES = {"divider", "membership", "support"}
BUCKETS = [*SPECTRA.keys(), *sorted(ROLES)]


def bucket_of(category: str | None) -> str:
    raw = (category or "").strip()
    if raw in ROLES:
        return raw
    if not raw:
        return ""
    return spectrum_of(raw)


def order_key(row: EmojiMapping) -> tuple:
    created = getattr(row, "created_at", None)
    stamp = created.timestamp() if created is not None else 0
    return (-(int(row.priority or 0)), stamp, str(row.id or ""))


def write_queue(rows: list[EmojiMapping]) -> None:
    """First row becomes the first choice. Later rows wait behind it."""
    total = len(rows)
    for index, row in enumerate(rows):
        row.priority = total - index


def queue_of(rows: list[EmojiMapping], bucket: str) -> list[EmojiMapping]:
    members = [row for row in rows if bucket_of(row.category) == bucket]
    members.sort(key=order_key)
    return members


async def load_rows(db: AsyncSession) -> list[EmojiMapping]:
    return list((await db.execute(select(EmojiMapping))).scalars().all())


async def append_ids(db: AsyncSession, ids: list[str]) -> None:
    """Put these rows at the end of whatever spectrum they now belong to."""
    wanted = [item for item in ids if item]
    if not wanted:
        return
    index = {item: pos for pos, item in enumerate(wanted)}
    rows = await load_rows(db)
    groups: dict[str, list[EmojiMapping]] = defaultdict(list)
    for row in rows:
        if row.id in index:
            groups[bucket_of(row.category)].append(row)
    for bucket, newcomers in groups.items():
        stayed = [row for row in rows if bucket_of(row.category) == bucket and row.id not in index]
        stayed.sort(key=order_key)
        newcomers.sort(key=lambda row: index.get(row.id, 10**9))
        write_queue(stayed + newcomers)


async def apply_queue(db: AsyncSession, bucket: str, ids: list[str]) -> list[EmojiMapping]:
    rows = await load_rows(db)
    members = queue_of(rows, bucket)
    by_id = {row.id: row for row in members}
    ordered: list[EmojiMapping] = []
    seen: set[str] = set()
    for item in ids:
        row = by_id.get(item)
        if row is None or row.id in seen:
            continue
        ordered.append(row)
        seen.add(row.id)
    rest = [row for row in members if row.id not in seen]
    final = ordered + rest
    write_queue(final)
    return final
