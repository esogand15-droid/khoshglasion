"""Cursor, daily balance and retry delays. No network and no model calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def oldest_unread(messages: list[dict], min_id: int, limit: int) -> tuple[list[dict], bool]:
    newer = [item for item in messages if int(item.get("id") or 0) > int(min_id or 0)]
    newer.sort(key=lambda item: int(item["id"]))
    size = max(1, int(limit or 1))
    page = newer[:size]
    return page, len(newer) > len(page)


def cursor_after(last_id: int, page: list[dict], handled: set[int], stop_before: int | None = None) -> int:
    """Advance only through ids this page fully handled, oldest first."""
    cursor = int(last_id or 0)
    for item in page:
        message_id = int(item["id"])
        if message_id <= cursor:
            continue
        if stop_before is not None and message_id >= int(stop_before):
            break
        if message_id not in handled:
            break
        cursor = message_id
    return cursor


def retry_delay_seconds(attempt: int) -> int:
    return min(900, 60 * (2 ** max(0, int(attempt) - 1)))


def next_retry_at(attempt: int, now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current + timedelta(seconds=retry_delay_seconds(attempt))


def allow_publish(
    category: str,
    published_today: dict[str, int],
    queued_categories: set[str],
    daily_cap: int,
    balance: bool,
) -> bool:
    total = sum(int(value) for value in published_today.values())
    if daily_cap and int(daily_cap) > 0 and total >= int(daily_cap):
        return False
    if not balance:
        return True
    mine = int(published_today.get(category, 0))
    rivals = [name for name in queued_categories if name and name != category]
    if not rivals:
        return True
    return all(mine <= int(published_today.get(name, 0)) for name in rivals)


def pick_balanced(drafts: list, slot_category: str | None, published_today: dict[str, int], daily_cap: int, balance: bool):
    queued = {getattr(item, "category", None) for item in drafts}
    pool = [item for item in drafts if not slot_category or getattr(item, "category", None) == slot_category]
    for item in pool:
        if allow_publish(getattr(item, "category", "") or "", published_today, queued, daily_cap, balance):
            return item
    return None
