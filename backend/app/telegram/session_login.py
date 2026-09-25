"""Panel login for the premium user session that edits channel posts.

Telegram's Telethon login is three real calls, not a made-up endpoint:
send_code_request, sign_in(code), and sign_in(password) only if Telegram
raises SessionPasswordNeededError. The auth key created by the first call
must be the same session used for the later calls, so the partial
StringSession is kept until the code is accepted.

The finished session string is stored in system_settings so the panel can
apply it without a Railway variable or a restart. It is never returned by
an API response, written to the audit log, or included in a backup.
"""
from __future__ import annotations

import logging
import re
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.system import SystemSetting
from backend.app.telegram.user_editor import (
    clear_credential_override,
    close_user_client,
    set_credential_override,
)

logger = logging.getLogger(__name__)

SOURCE_KEY = "tg_session_source"
API_ID_KEY = "tg_api_id"
API_HASH_KEY = "tg_api_hash"
SESSION_KEY = "tg_session_string"
USER_ID_KEY = "tg_session_user_id"
USERNAME_KEY = "tg_session_username"
PREMIUM_KEY = "tg_session_premium"
LOGIN_PHONE = "tg_login_phone"
LOGIN_HASH = "tg_login_hash"
LOGIN_SESSION = "tg_login_session"
LOGIN_API_ID = "tg_login_api_id"
LOGIN_API_HASH = "tg_login_api_hash"
LOGIN_STEP = "tg_login_step"
LOGIN_DELIVERY = "tg_login_delivery"
LOGIN_CODE_LENGTH = "tg_login_code_length"

SECRET_SETTING_KEYS = frozenset({
    API_HASH_KEY,
    SESSION_KEY,
    LOGIN_HASH,
    LOGIN_SESSION,
    LOGIN_API_HASH,
    LOGIN_PHONE,
})
BACKUP_SKIP_KEYS = SECRET_SETTING_KEYS | {
    API_ID_KEY,
    SOURCE_KEY,
    LOGIN_API_ID,
    LOGIN_STEP,
    LOGIN_DELIVERY,
    LOGIN_CODE_LENGTH,
    USER_ID_KEY,
    USERNAME_KEY,
    PREMIUM_KEY,
    "bot_token",
    "webhook_secret",
    "jwt_secret",
}
PENDING_KEYS = (
    LOGIN_PHONE,
    LOGIN_HASH,
    LOGIN_SESSION,
    LOGIN_API_ID,
    LOGIN_API_HASH,
    LOGIN_STEP,
    LOGIN_DELIVERY,
    LOGIN_CODE_LENGTH,
)

CODE_WAIT_SECONDS = 15
_DIGIT_TABLE = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_pending_client = None
_last_code_at = 0.0
_opener = None
_status_probe = None


class SessionLoginError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def is_secret_setting(key: str) -> bool:
    return key in BACKUP_SKIP_KEYS


def ascii_digits(raw: str) -> str:
    return (raw or "").translate(_DIGIT_TABLE)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", ascii_digits(raw))
    if digits.startswith("00"):
        digits = digits[2:]
    # 0912… and the same mobile without the trunk zero. No other country is guessed.
    if digits.startswith("0") and len(digits) == 11:
        digits = "98" + digits[1:]
    elif len(digits) == 10 and digits.startswith("9"):
        digits = "98" + digits
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise SessionLoginError("شماره را با کد کشور بنویس، مثل ‎+98912…")
    return digits


def clean_code(raw: str) -> str:
    return re.sub(r"\s+", "", ascii_digits(raw))


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 6:
        return ""
    hidden = max(0, len(digits) - 7)
    return f"+{digits[:3]}{'•' * hidden}{digits[-4:]}"


def delivery_text(sent) -> str:
    kind = type(getattr(sent, "type", None)).__name__
    hints = {
        "SentCodeTypeApp": "کد داخل خود تلگرام، در چت Telegram، فرستاده شد. پیامک نیست.",
        "SentCodeTypeSms": "کد با پیامک فرستاده شد.",
        "SentCodeTypeCall": "تلگرام با تماس صوتی کد را می‌گوید.",
        "SentCodeTypeFlashCall": "تلگرام یک تماس کوتاه می‌زند. کد، رقم‌های آخر شمارهٔ تماس است.",
        "SentCodeTypeMissedCall": "تلگرام یک تماس بی‌پاسخ می‌زند.",
        "SentCodeTypeFragmentSms": "کد از طریق Fragment پیامک شد.",
        "SentCodeTypeFirebaseSms": "کد با پیامک فرستاده شد.",
        "SentCodeTypeEmailCode": "کد به ایمیل متصل به تلگرام فرستاده شد.",
        "SentCodeTypeSetUpEmailRequired": "تلگرام اول می‌خواهد ایمیل را در خود اپ تنظیم کنی. بعد دوباره کد بگیر.",
        "SentCodeTypeSmsPhrase": "کد به شکل یک عبارت پیامکی آمد.",
        "SentCodeTypeSmsWord": "کد به شکل یک کلمهٔ پیامکی آمد.",
    }
    return hints.get(kind, "کد را از تلگرام بگیر و همین‌جا وارد کن.")


def code_length(sent) -> int | None:
    length = getattr(getattr(sent, "type", None), "length", None)
    if isinstance(length, int) and 1 <= length <= 16:
        return length
    return None


def _login_error(exc: Exception) -> SessionLoginError:
    name = type(exc).__name__
    if name == "FloodWaitError":
        seconds = getattr(exc, "seconds", None)
        if isinstance(seconds, int) and seconds > 0:
            return SessionLoginError(f"تلگرام گفته {seconds} ثانیه صبر کن، بعد دوباره کد بگیر.", 429)
        return SessionLoginError("تلگرام موقتاً درخواست را محدود کرده. کمی بعد دوباره تلاش کن.", 429)
    messages = {
        "PhoneNumberInvalidError": "شماره نامعتبر است. با کد کشور بنویس، مثل ‎+98912…",
        "PhoneNumberBannedError": "تلگرام این شماره را برای ورود محدود کرده.",
        "PhoneNumberFloodError": "برای این شماره بیش از حد کد خواسته شده. کمی بعد دوباره تلاش کن.",
        "PhoneNumberUnoccupiedError": "این شماره در تلگرام حساب ندارد.",
        "PhoneCodeInvalidError": "کد اشتباه است.",
        "PhoneCodeExpiredError": "کد منقضی شد. دوباره کد بگیر.",
        "PhoneCodeEmptyError": "کد خالی است.",
        "PhoneCodeHashEmptyError": "درخواست کد منقضی شد. دوباره کد بگیر.",
        "PhoneHashExpiredError": "درخواست کد منقضی شد. دوباره کد بگیر.",
        "PasswordHashInvalidError": "رمز دومرحله‌ای اشتباه است.",
        "ApiIdInvalidError": "API ID یا API hash با هم جور نیستند. از my.telegram.org همان جفت را کپی کن.",
        "ApiIdPublishedFloodError": "این API ID عمومی است و تلگرام آن را محدود کرده. از my.telegram.org برای همین اکانت یک جفت تازه بساز.",
        "SendCodeUnavailableError": "تلگرام الان کد نمی‌فرستد. کمی بعد دوباره تلاش کن.",
        "AuthRestartError": "تلگرام ورود را از نو خواست. انصراف بده و دوباره کد بگیر.",
    }
    if name in messages:
        return SessionLoginError(messages[name])
    logger.warning("Telegram login failed: %s", name)
    return SessionLoginError("ورود تلگرام انجام نشد. شماره، API ID و API hash را دوباره بررسی کن.")


def set_client_opener(opener) -> None:
    global _opener
    _opener = opener


def set_status_probe(probe) -> None:
    global _status_probe
    _status_probe = probe


def reset_login_runtime() -> None:
    global _pending_client, _last_code_at, _opener, _status_probe
    _pending_client = None
    _last_code_at = 0.0
    _opener = None
    _status_probe = None
    clear_credential_override()


async def _open_client(api_id: str, api_hash: str, session_string: str):
    if _opener is not None:
        return await _opener(int(api_id), api_hash, session_string)
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(session_string or ""), int(api_id), api_hash)
    await client.connect()
    return client


def _session_string(client) -> str:
    session = getattr(client, "session", None)
    save = getattr(session, "save", None)
    if callable(save):
        return str(save() or "")
    direct = getattr(client, "save", None)
    if callable(direct):
        return str(direct() or "")
    return ""


async def _drop_pending_client() -> None:
    global _pending_client
    client = _pending_client
    _pending_client = None
    if client is None:
        return
    try:
        await client.disconnect()
    except Exception:
        logger.warning("Pending Telegram login client did not disconnect cleanly")


async def _values(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(SystemSetting))).scalars().all()
    return {row.key: row.value or "" for row in rows}


async def _put(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=value, description="telegram session"))
    else:
        row.value = value
    await db.flush()


async def _clear_pending(db: AsyncSession) -> None:
    for key in PENDING_KEYS:
        await _put(db, key, "")
    await _drop_pending_client()


async def refresh_user_credentials(db: AsyncSession) -> None:
    values = await _values(db)
    if values.get(SOURCE_KEY) == "panel":
        set_credential_override(values.get(API_ID_KEY, ""), values.get(API_HASH_KEY, ""), values.get(SESSION_KEY, ""))
        return
    clear_credential_override()


def _profile(values: dict[str, str]) -> dict:
    premium_raw = values.get(PREMIUM_KEY, "")
    premium = None if premium_raw == "" else premium_raw == "true"
    user_id = values.get(USER_ID_KEY, "")
    return {
        "user_id": int(user_id) if user_id.isdigit() else None,
        "username": values.get(USERNAME_KEY) or None,
        "premium": premium,
    }


async def session_public_status(db: AsyncSession) -> dict:
    await refresh_user_credentials(db)
    values = await _values(db)
    from backend.app.telegram.user_editor import session_configured

    step = values.get(LOGIN_STEP) or None
    if step not in {"code", "password"}:
        step = None
    length_raw = values.get(LOGIN_CODE_LENGTH, "")
    return {
        "configured": session_configured(),
        "source": "panel" if values.get(SOURCE_KEY) == "panel" else ("env" if session_configured() else None),
        "pending_step": step,
        "phone_masked": mask_phone(values.get(LOGIN_PHONE, "")) if step else "",
        "delivery": values.get(LOGIN_DELIVERY) or None if step else None,
        "code_length": int(length_raw) if step and length_raw.isdigit() else None,
        "api_id_set": bool(values.get(API_ID_KEY) or values.get(LOGIN_API_ID)),
        **_profile(values),
    }


def _public_login(step: str, phone: str, delivery: str | None = None, length: int | None = None, **extra) -> dict:
    payload = {
        "ok": True,
        "step": step,
        "phone_masked": mask_phone(phone),
        "delivery": delivery,
        "code_length": length,
    }
    payload.update(extra)
    return payload


def _validate_api(api_id: str, api_hash: str) -> tuple[str, str]:
    raw_id = str(api_id or "").strip()
    raw_hash = str(api_hash or "").strip()
    if not raw_id.isdigit() or not 1 <= len(raw_id) <= 12:
        raise SessionLoginError("API ID باید عدد my.telegram.org باشد.")
    if not re.fullmatch(r"[A-Za-z0-9]{16,64}", raw_hash):
        raise SessionLoginError("API hash را کامل از my.telegram.org کپی کن.")
    return raw_id, raw_hash


async def start_login(db: AsyncSession, api_id: str, api_hash: str, phone: str) -> dict:
    global _pending_client, _last_code_at
    api_id, api_hash = _validate_api(api_id, api_hash)
    normalized = normalize_phone(phone)
    now = time.monotonic()
    if _last_code_at and now - _last_code_at < CODE_WAIT_SECONDS:
        wait = int(CODE_WAIT_SECONDS - (now - _last_code_at)) + 1
        raise SessionLoginError(f"کد همین الان فرستاده شد. {wait} ثانیه صبر کن.", 429)
    await _drop_pending_client()
    client = None
    try:
        client = await _open_client(api_id, api_hash, "")
        sent = await client.send_code_request(normalized)
    except SessionLoginError:
        if client is not None:
            await client.disconnect()
        raise
    except Exception as exc:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        raise _login_error(exc) from None
    saved = _session_string(client)
    phone_hash = str(getattr(sent, "phone_code_hash", "") or "")
    if not saved or not phone_hash:
        try:
            await client.disconnect()
        except Exception:
            pass
        raise SessionLoginError("نشست موقت تلگرام ساخته نشد. دوباره کد بگیر.")
    hint = delivery_text(sent)
    length = code_length(sent)
    _pending_client = client
    _last_code_at = now
    await _put(db, LOGIN_PHONE, normalized)
    await _put(db, LOGIN_HASH, phone_hash)
    await _put(db, LOGIN_SESSION, saved)
    await _put(db, LOGIN_API_ID, api_id)
    await _put(db, LOGIN_API_HASH, api_hash)
    await _put(db, LOGIN_STEP, "code")
    await _put(db, LOGIN_DELIVERY, hint)
    await _put(db, LOGIN_CODE_LENGTH, "" if length is None else str(length))
    return _public_login("code", normalized, hint, length)


async def _pending(db: AsyncSession) -> tuple[dict[str, str], object]:
    global _pending_client
    values = await _values(db)
    if values.get(LOGIN_STEP) not in {"code", "password"} or not values.get(LOGIN_HASH) or not values.get(LOGIN_SESSION):
        raise SessionLoginError("اول از پنل کد تلگرام را بگیر.")
    client = _pending_client
    connected = bool(client is not None and getattr(client, "is_connected", lambda: False)())
    if not connected:
        try:
            client = await _open_client(values.get(LOGIN_API_ID, ""), values.get(LOGIN_API_HASH, ""), values.get(LOGIN_SESSION, ""))
        except SessionLoginError:
            raise
        except Exception as exc:
            raise _login_error(exc) from None
        _pending_client = client
    return values, client


async def _finish(db: AsyncSession, client, values: dict[str, str], user) -> dict:
    saved = _session_string(client)
    if not saved:
        raise SessionLoginError("رشتهٔ نشست بعد از ورود ساخته نشد. دوباره کد بگیر.")
    user_id = getattr(user, "id", None)
    username = getattr(user, "username", None)
    premium = bool(getattr(user, "premium", False))
    await _put(db, SOURCE_KEY, "panel")
    await _put(db, API_ID_KEY, values.get(LOGIN_API_ID, ""))
    await _put(db, API_HASH_KEY, values.get(LOGIN_API_HASH, ""))
    await _put(db, SESSION_KEY, saved)
    await _put(db, USER_ID_KEY, "" if user_id is None else str(user_id))
    await _put(db, USERNAME_KEY, username or "")
    await _put(db, PREMIUM_KEY, "true" if premium else "false")
    await _clear_pending(db)
    await close_user_client()
    set_credential_override(values.get(LOGIN_API_ID, ""), values.get(LOGIN_API_HASH, ""), saved)
    return {
        "ok": True,
        "step": "ready",
        "configured": True,
        "user_id": user_id,
        "username": username,
        "premium": premium,
        "phone_masked": mask_phone(values.get(LOGIN_PHONE, "")),
    }


async def submit_code(db: AsyncSession, code: str) -> dict:
    cleaned = clean_code(code)
    if not cleaned or len(cleaned) > 16:
        raise SessionLoginError("کد تلگرام را وارد کن.")
    values, client = await _pending(db)
    if values.get(LOGIN_STEP) != "code":
        raise SessionLoginError("تلگرام رمز دومرحله‌ای می‌خواهد، نه کد.")
    try:
        from telethon.errors import SessionPasswordNeededError
    except ImportError:
        SessionPasswordNeededError = ()  # type: ignore[assignment]
    try:
        user = await client.sign_in(
            values.get(LOGIN_PHONE, ""),
            cleaned,
            phone_code_hash=values.get(LOGIN_HASH, ""),
        )
    except SessionPasswordNeededError:
        saved = _session_string(client)
        if saved:
            await _put(db, LOGIN_SESSION, saved)
        await _put(db, LOGIN_STEP, "password")
        return _public_login("password", values.get(LOGIN_PHONE, ""), "این اکانت رمز دومرحله‌ای دارد. همان رمز تلگرام را همین‌جا وارد کن.")
    except SessionLoginError:
        raise
    except Exception as exc:
        raise _login_error(exc) from None
    return await _finish(db, client, values, user)


async def submit_password(db: AsyncSession, password: str) -> dict:
    secret = password or ""
    if not secret or len(secret) > 256:
        raise SessionLoginError("رمز دومرحله‌ای را وارد کن.")
    values, client = await _pending(db)
    if values.get(LOGIN_STEP) != "password":
        raise SessionLoginError("اول کد تلگرام را وارد کن.")
    try:
        user = await client.sign_in(password=secret)
    except SessionLoginError:
        raise
    except Exception as exc:
        raise _login_error(exc) from None
    return await _finish(db, client, values, user)


async def resend_login_code(db: AsyncSession) -> dict:
    global _last_code_at
    now = time.monotonic()
    if _last_code_at and now - _last_code_at < CODE_WAIT_SECONDS:
        wait = int(CODE_WAIT_SECONDS - (now - _last_code_at)) + 1
        raise SessionLoginError(f"کد همین الان فرستاده شد. {wait} ثانیه صبر کن.", 429)
    values, client = await _pending(db)
    if values.get(LOGIN_STEP) != "code":
        raise SessionLoginError("الان رمز دومرحله‌ای لازم است، نه کد تازه.")
    phone = values.get(LOGIN_PHONE, "")
    phone_hash = values.get(LOGIN_HASH, "")
    try:
        from telethon.tl.functions.auth import ResendCodeRequest
        sent = await client(ResendCodeRequest(phone, phone_hash))
    except Exception as exc:
        if type(exc).__name__ in {"PhoneCodeExpiredError", "PhoneHashExpiredError", "PhoneCodeHashEmptyError"}:
            try:
                sent = await client.send_code_request(phone)
            except Exception as nested:
                raise _login_error(nested) from None
        else:
            raise _login_error(exc) from None
    saved = _session_string(client)
    new_hash = str(getattr(sent, "phone_code_hash", "") or "")
    if not saved or not new_hash:
        raise SessionLoginError("کد دوباره فرستاده نشد. کمی بعد تلاش کن.")
    hint = delivery_text(sent)
    length = code_length(sent)
    _last_code_at = now
    await _put(db, LOGIN_HASH, new_hash)
    await _put(db, LOGIN_SESSION, saved)
    await _put(db, LOGIN_DELIVERY, hint)
    await _put(db, LOGIN_CODE_LENGTH, "" if length is None else str(length))
    return _public_login("code", phone, hint, length)


async def check_saved_session(db: AsyncSession) -> dict:
    await refresh_user_credentials(db)
    from backend.app.telegram.user_editor import session_configured, user_session_status

    if not session_configured():
        public = await session_public_status(db)
        public["authorized"] = False
        return public
    try:
        live = await (_status_probe() if _status_probe is not None else user_session_status())
    except Exception as exc:
        logger.warning("Telegram session check failed: %s", type(exc).__name__)
        live = {"authorized": False}
    if live.get("authorized"):
        user_id = live.get("user_id")
        await _put(db, USER_ID_KEY, "" if user_id is None else str(user_id))
        await _put(db, USERNAME_KEY, live.get("username") or "")
        if live.get("premium") is not None:
            await _put(db, PREMIUM_KEY, "true" if live.get("premium") else "false")
    public = await session_public_status(db)
    public["authorized"] = bool(live.get("authorized"))
    return public


async def close_pending_login() -> None:
    await _drop_pending_client()


async def _logout_saved(values: dict[str, str]) -> None:
    session = values.get(SESSION_KEY, "")
    api_id = values.get(API_ID_KEY, "")
    api_hash = values.get(API_HASH_KEY, "")
    if not (session and api_id and api_hash):
        return
    await _drop_pending_client()
    try:
        client = await _open_client(api_id, api_hash, session)
    except Exception as exc:
        logger.warning("Could not reopen Telegram session to log out: %s", type(exc).__name__)
        return
    try:
        logout = getattr(client, "log_out", None)
        if callable(logout):
            await logout()
    except Exception as exc:
        logger.warning("Telegram log_out failed: %s", type(exc).__name__)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def cancel_login(db: AsyncSession) -> dict:
    global _last_code_at
    await _clear_pending(db)
    _last_code_at = 0.0
    return {"ok": True, "step": None}


async def disconnect_session(db: AsyncSession) -> dict:
    await _logout_saved(await _values(db))
    await cancel_login(db)
    await _put(db, SOURCE_KEY, "panel")
    await _put(db, API_ID_KEY, "")
    await _put(db, API_HASH_KEY, "")
    await _put(db, SESSION_KEY, "")
    await _put(db, USER_ID_KEY, "")
    await _put(db, USERNAME_KEY, "")
    await _put(db, PREMIUM_KEY, "")
    await close_user_client()
    set_credential_override("", "", "")
    return {"ok": True, "configured": False, "step": None}
