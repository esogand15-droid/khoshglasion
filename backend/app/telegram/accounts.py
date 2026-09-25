"""Several Telegram user sessions, each with a job.

emoji edits channel posts with animated emoji. news joins public news
channels and reads them. One premium account may hold both jobs. Session
strings stay in the database and this process; public views never include
them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.telegram_account import TelegramAccount

MAX_ACCOUNTS = 5
_registry: list[dict] = []


class AccountError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def clear_registry() -> None:
    _registry.clear()


def parse_roles(raw: str | None) -> str:
    text = (raw or "both").strip().lower().replace(" ", "")
    if text in {"both", "all", "emoji,news", "news,emoji"}:
        return "emoji,news"
    parts: list[str] = []
    if text in {"emoji", "premium"} or "emoji" in text:
        parts.append("emoji")
    if text in {"news", "collect"} or "news" in text:
        parts.append("news")
    if not parts:
        raise AccountError("نقش باید ایموجی، خبر، یا هر دو باشد.")
    return ",".join(parts)


def roles_of(raw: str | None) -> set[str]:
    return {part for part in (raw or "").split(",") if part in {"emoji", "news"}}


def public_account(row: TelegramAccount) -> dict:
    user_id = row.user_id or ""
    return {
        "id": row.id,
        "label": row.label or None,
        "phone_masked": row.phone_masked or "",
        "user_id": int(user_id) if user_id.isdigit() else None,
        "username": row.username or None,
        "premium": row.premium,
        "roles": sorted(roles_of(row.roles)),
        "enabled": bool(row.enabled),
        "join_public": bool(row.join_public),
        "last_error": row.last_error or None,
    }


def pick_emoji() -> dict | None:
    enabled = [row for row in _registry if row.get("enabled") and "emoji" in row.get("roles", set())]
    premium = [row for row in enabled if row.get("premium") is True]
    return (premium or enabled or [None])[0]


def pick_news() -> dict | None:
    enabled = [row for row in _registry if row.get("enabled") and "news" in row.get("roles", set())]
    plain = [row for row in enabled if row.get("premium") is False]
    return (plain or enabled or [None])[0]


def news_may_join() -> bool:
    picked = pick_news()
    if picked is None:
        return False
    return bool(picked.get("join_public", False))


async def list_rows(db: AsyncSession) -> list[TelegramAccount]:
    return list((await db.execute(select(TelegramAccount).order_by(TelegramAccount.created_at))).scalars().all())


async def public_accounts(db: AsyncSession) -> list[dict]:
    return [public_account(row) for row in await list_rows(db)]


def _remember(rows: list[TelegramAccount]) -> None:
    _registry.clear()
    for row in rows:
        if not row.enabled or not (row.api_id and row.api_hash and row.session_string):
            continue
        _registry.append({
            "id": row.id,
            "api_id": row.api_id,
            "api_hash": row.api_hash,
            "session": row.session_string,
            "roles": roles_of(row.roles),
            "premium": row.premium,
            "enabled": True,
            "username": row.username,
            "user_id": row.user_id,
            "join_public": bool(row.join_public),
        })


async def load_registry(db: AsyncSession) -> None:
    _remember(await list_rows(db))


async def import_legacy_panel_account(db: AsyncSession, values: dict[str, str]) -> None:
    session = (values.get("tg_session_string") or "").strip()
    if values.get("tg_session_source") != "panel" or not session:
        return
    rows = await list_rows(db)
    if any(row.session_string == session for row in rows):
        return
    if len(rows) >= MAX_ACCOUNTS:
        return
    premium_raw = values.get("tg_session_premium", "")
    premium = None if premium_raw == "" else premium_raw == "true"
    db.add(TelegramAccount(
        label=values.get("tg_session_username") or "نشست قبلی",
        phone_masked="",
        user_id=values.get("tg_session_user_id") or None,
        username=values.get("tg_session_username") or None,
        premium=premium,
        roles="emoji,news",
        enabled=True,
        join_public=False,
        api_id=values.get("tg_api_id") or "",
        api_hash=values.get("tg_api_hash") or "",
        session_string=session,
    ))
    await db.flush()


async def save_logged_in_account(
    db: AsyncSession,
    *,
    user_id: str,
    username: str,
    premium: bool,
    phone_masked: str,
    api_id: str,
    api_hash: str,
    session: str,
    roles: str,
    label: str,
) -> TelegramAccount:
    rows = await list_rows(db)
    row = next((item for item in rows if user_id and item.user_id == user_id), None)
    if row is None and len(rows) >= MAX_ACCOUNTS:
        raise AccountError("حداکثر ۵ نشست فعال می‌توانی وصل کنی. یکی را قطع کن.")
    if row is None:
        row = TelegramAccount(user_id=user_id or None)
        db.add(row)
    row.label = (label or username or row.label or "نشست")[:64]
    row.phone_masked = phone_masked or row.phone_masked
    row.user_id = user_id or row.user_id
    row.username = username or None
    row.premium = premium
    row.roles = roles
    row.enabled = True
    if row.join_public is None:
        row.join_public = False
    row.api_id = api_id
    row.api_hash = api_hash
    row.session_string = session
    row.last_error = None
    await db.flush()
    return row


async def delete_matching(db: AsyncSession, user_id: str, session: str) -> None:
    for row in await list_rows(db):
        if (user_id and row.user_id == user_id) or (session and row.session_string == session):
            await db.delete(row)
    await db.flush()


async def get_account(db: AsyncSession, account_id: str) -> TelegramAccount:
    row = await db.get(TelegramAccount, account_id)
    if row is None:
        raise AccountError("این نشست پیدا نشد.", 404)
    return row


async def update_account(
    db: AsyncSession,
    account_id: str,
    *,
    roles: str | None = None,
    enabled: bool | None = None,
    label: str | None = None,
    join_public: bool | None = None,
) -> dict:
    row = await get_account(db, account_id)
    if roles is not None:
        row.roles = parse_roles(roles)
    if enabled is not None:
        row.enabled = enabled
    if label is not None:
        row.label = label.strip()[:64] or row.label
    if join_public is not None:
        row.join_public = join_public
    if not roles_of(row.roles):
        raise AccountError("حداقل یک نقش لازم است: ایموجی یا خبر.")
    await db.flush()
    return public_account(row)


async def apply_command(db: AsyncSession, text: str) -> str:
    parts = (text or "").split()
    rows = await list_rows(db)
    if len(parts) < 3:
        return _list_text(rows) + "\nنمونه: /session 1 both"
    try:
        index = int(parts[1])
    except ValueError:
        return "شمارهٔ نشست را بنویس. نمونه: /session 2 news"
    if not 1 <= index <= len(rows):
        return "این شماره در فهرست نشست‌ها نیست. /sessions"
    row = rows[index - 1]
    action = parts[2].lower()
    if action in {"off", "0", "disable"}:
        row.enabled = False
    elif action in {"on", "1", "enable"}:
        row.enabled = True
    elif action in {"both", "emoji", "news", "premium"}:
        row.roles = parse_roles(action)
    else:
        return "نقش را both، emoji، news، on یا off بنویس."
    await db.flush()
    await load_registry(db)
    return f"نشست {index} به‌روز شد.\n" + _list_text(await list_rows(db))


def _list_text(rows: list[TelegramAccount]) -> str:
    if not rows:
        return "نشست فعالی در پنل نیست. از تنظیمات، تب نشست، اکانت را وصل کن."
    lines = ["نشست‌های پنل:"]
    for index, row in enumerate(rows, start=1):
        name = f"@{row.username}" if row.username else (row.label or "بدون نام")
        kind = "پرمیوم" if row.premium else "معمولی" if row.premium is False else "نامشخص"
        jobs = []
        roles = roles_of(row.roles)
        if "emoji" in roles:
            jobs.append("ایموجی")
        if "news" in roles:
            jobs.append("خبر")
        state = "روشن" if row.enabled else "خاموش"
        lines.append(f"{index}. {name} · {kind} · {' و '.join(jobs) or 'بدون نقش'} · {state}")
    lines.append("تغییر نقش: /session 1 both یا /session 2 news")
    lines.append("عضویت در کانال عمومی: /join @channel")
    return "\n".join(lines)


async def sessions_text(db: AsyncSession) -> str:
    return _list_text(await list_rows(db))
