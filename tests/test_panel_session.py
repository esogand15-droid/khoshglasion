import asyncio
import inspect
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.system import backup, telegram_session_code, telegram_session_start
from backend.app.api.system import SessionCode, SessionStart
from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.models.audit import AuditLog
from backend.app.models.system import SystemSetting
from backend.app.telegram import session_login
from backend.app.logging_config.setup import redact_secrets
from backend.app.telegram.session_login import (
    SessionLoginError,
    check_saved_session,
    disconnect_session,
    normalize_phone,
    resend_login_code,
    reset_login_runtime,
    session_public_status,
    set_client_opener,
    set_status_probe,
    start_login,
    submit_code,
    submit_password,
)
from backend.app.telegram.user_editor import current_credentials, session_configured
import backend.app.models  # noqa: F401


API_HASH = "abcDEF1234567890hash"
SESSION_SECRET = "partial-session-secret"
PASSWORD = "panel-2fa-secret"
PHONE = "09123456789"
NORMAL_PHONE = "989123456789"


class SentCodeTypeApp:
    length = 5


class Sent:
    type = SentCodeTypeApp()
    phone_code_hash = "hash-secret-do-not-leak"


class User:
    id = 4242
    username = "goldowner"
    premium = True


class FakeClient:
    opened = []
    instances = []

    def __init__(self, api_id, api_hash, session_string):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.connected = True
        self.session = self
        self.calls = []
        self.logged_out = False
        FakeClient.opened.append((api_id, api_hash, session_string))
        FakeClient.instances.append(self)

    def save(self):
        if self.session_string:
            return "saved-" + self.session_string
        return SESSION_SECRET

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def log_out(self):
        self.logged_out = True
        self.connected = False

    async def send_code_request(self, phone):
        self.calls.append(("send", phone))
        if phone == "989000000042":
            from telethon.errors import FloodWaitError
            raise FloodWaitError(None, 42)
        return Sent()

    async def __call__(self, request):
        self.calls.append(("rpc", type(request).__name__, getattr(request, "phone_code_hash", None)))
        if type(request).__name__ != "ResendCodeRequest":
            raise RuntimeError(type(request).__name__)
        return type("Resent", (), {"type": SentCodeTypeApp(), "phone_code_hash": "hash-secret-resent-do-not-leak"})()

    async def sign_in(self, phone=None, code=None, password=None, phone_code_hash=None):
        self.calls.append(("sign", phone, code, password, phone_code_hash))
        if password is not None:
            if password != PASSWORD:
                from telethon.errors import PasswordHashInvalidError
                raise PasswordHashInvalidError(None)
            return User()
        if phone_code_hash not in {Sent.phone_code_hash, "hash-secret-resent-do-not-leak"}:
            from telethon.errors import PhoneCodeInvalidError
            raise PhoneCodeInvalidError(None)
        if code == "00000":
            from telethon.errors import PhoneCodeInvalidError
            raise PhoneCodeInvalidError(None)
        if code == "22222":
            from telethon.errors import SessionPasswordNeededError
            raise SessionPasswordNeededError(None)
        return User()


async def open_fake(api_id, api_hash, session_string):
    return FakeClient(api_id, api_hash, session_string)


def _session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _secrets_absent(payload):
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    for secret in (API_HASH, SESSION_SECRET, Sent.phone_code_hash, PASSWORD, NORMAL_PHONE, "saved-" + SESSION_SECRET):
        assert secret not in raw, secret
    return raw


def test_phone_normalization_only_adds_iran_code_for_local_mobile():
    assert normalize_phone("0912 345 6789") == NORMAL_PHONE
    assert normalize_phone("+98 912 345 6789") == NORMAL_PHONE
    assert normalize_phone("00989123456789") == NORMAL_PHONE
    assert normalize_phone("۰۹۱۲۳۴۵۶۷۸۹") == NORMAL_PHONE
    assert normalize_phone("9123456789") == NORMAL_PHONE
    assert normalize_phone("۹۱۲۳۴۵۶۷۸۹") == NORMAL_PHONE
    assert normalize_phone("091234567") == "091234567"
    assert normalize_phone("441234567890") == "441234567890"
    try:
        normalize_phone("12345")
    except SessionLoginError as exc:
        assert "کد کشور" in exc.message
    else:
        raise AssertionError("short number was accepted")


def test_panel_login_survives_restart_and_hides_secrets():
    async def run():
        FakeClient.opened = []
        FakeClient.instances = []
        session_login.CODE_WAIT_SECONDS = 0
        set_client_opener(open_fake)
        records = []

        class Grab(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Grab()
        logger = logging.getLogger("backend.app.telegram.session_login")
        logger.addHandler(handler)
        engine, factory = _session()
        settings = get_settings()
        old = (settings.tg_api_id, settings.tg_api_hash, settings.tg_session_string)
        settings.tg_api_id = "111"
        settings.tg_api_hash = "envhashenvhashenv1"
        settings.tg_session_string = "env-session-must-not-return"
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with factory() as db:
                started = await start_login(db, "12345", API_HASH, PHONE)
                assert started["step"] == "code"
                assert started["code_length"] == 5
                assert "پیامک نیست" in started["delivery"]
                assert FakeClient.opened[0][2] == ""
                assert FakeClient.opened[0][1] == API_HASH
                _secrets_absent(started)

                session_login._pending_client = None
                bad = None
                try:
                    await submit_code(db, "00000")
                except SessionLoginError as exc:
                    bad = exc
                assert bad is not None and bad.message == "کد اشتباه است."
                assert FakeClient.opened[-1][2] == SESSION_SECRET
                assert FakeClient.instances[-1].calls[-1] == ("sign", NORMAL_PHONE, "00000", None, Sent.phone_code_hash)
                assert FakeClient.instances[0].calls[0] == ("send", NORMAL_PHONE)

                waiting = await submit_code(db, "22222")
                assert waiting["step"] == "password"
                _secrets_absent(waiting)
                try:
                    await submit_password(db, "wrong-pass")
                except SessionLoginError as exc:
                    assert exc.message == "رمز دومرحله‌ای اشتباه است."
                else:
                    raise AssertionError("bad 2FA password was accepted")

                ready = await submit_password(db, PASSWORD)
                assert ready["step"] == "ready"
                assert ready["premium"] is True
                assert ready["username"] == "goldowner"
                _secrets_absent(ready)
                status = await session_public_status(db)
                assert status["configured"] is True
                assert status["source"] == "panel"
                assert status["pending_step"] is None
                _secrets_absent(status)
                assert current_credentials()[2] == "saved-" + SESSION_SECRET
                assert session_configured() is True

                dumped = await backup(include_secrets=True, db=db, admin=None)
                raw_backup = _secrets_absent(dumped)
                assert "tg_session_string" not in raw_backup
                assert "tg_api_hash" not in raw_backup
                stored = (await db.execute(select(SystemSetting).where(SystemSetting.key == "tg_session_string"))).scalar_one()
                assert stored.value == "saved-" + SESSION_SECRET

                class Admin:
                    id = "1"
                    username = "owner"
                    role = "OWNER"

                class Request:
                    class client:
                        host = "127.0.0.1"

                await disconnect_session(db)
                assert session_configured() is False
                assert any(client.logged_out for client in FakeClient.instances)
                logged = [item for item in FakeClient.opened if item[2] == "saved-" + SESSION_SECRET]
                assert logged, FakeClient.opened
                still_hidden = await session_public_status(db)
                assert still_hidden["configured"] is False
                assert still_hidden["source"] == "panel"
                assert "env-session-must-not-return" not in json.dumps(still_hidden)

                flooded = None
                try:
                    await telegram_session_start(
                        SessionStart(api_id="12345", api_hash=API_HASH, phone="+989000000042"),
                        Request(),
                        db,
                        Admin(),
                    )
                except Exception as exc:
                    flooded = exc
                assert flooded is not None
                assert flooded.status_code == 429
                assert "42" in flooded.detail
                audits = (await db.execute(select(AuditLog))).scalars().all()
                assert audits == [] or all(API_HASH not in (row.new_value or "") for row in audits)
                for row in audits:
                    assert PASSWORD not in (row.new_value or "")
                    assert Sent.phone_code_hash not in (row.new_value or "")
        finally:
            logger.removeHandler(handler)
            settings.tg_api_id, settings.tg_api_hash, settings.tg_session_string = old
            reset_login_runtime()
            session_login.CODE_WAIT_SECONDS = 15
            await engine.dispose()
        joined = "\n".join(records)
        for secret in (API_HASH, SESSION_SECRET, Sent.phone_code_hash, PASSWORD, "env-session-must-not-return"):
            assert secret not in joined

    asyncio.run(run())


def test_direct_code_login_and_env_fallback():
    async def run():
        FakeClient.opened = []
        FakeClient.instances = []
        session_login.CODE_WAIT_SECONDS = 0
        set_client_opener(open_fake)
        engine, factory = _session()
        settings = get_settings()
        old = (settings.tg_api_id, settings.tg_api_hash, settings.tg_session_string)
        settings.tg_api_id = "222"
        settings.tg_api_hash = "envhashenvhashenv1"
        settings.tg_session_string = "env-session-must-not-return"
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with factory() as db:
                before = await session_public_status(db)
                assert before["configured"] is True
                assert before["source"] == "env"
                assert "env-session-must-not-return" not in json.dumps(before)

                db.add(SystemSetting(key="tg_session_source", value="panel", description="test"))
                await db.flush()
                blocked = await session_public_status(db)
                assert blocked["configured"] is False
                assert blocked["source"] == "panel"
                await db.execute(SystemSetting.__table__.delete())
                await db.flush()
                reset_login_runtime()
                set_client_opener(open_fake)

                class Admin:
                    id = "1"
                    username = "owner"
                    role = "OWNER"

                class Request:
                    class client:
                        host = "10.0.0.8"

                result = await telegram_session_start(
                    SessionStart(api_id="12345", api_hash=API_HASH, phone=PHONE),
                    Request(),
                    db,
                    Admin(),
                )
                assert result["phone_masked"].endswith("6789")
                assert NORMAL_PHONE not in json.dumps(result)
                done = await telegram_session_code(SessionCode(code="12345"), Request(), db, Admin())
                assert done["step"] == "ready"
                _secrets_absent(done)
                audit = (await db.execute(select(AuditLog))).scalars().all()
                blob = " ".join((row.new_value or "") + (row.old_value or "") for row in audit)
                assert API_HASH not in blob
                assert "12345" not in blob
                assert Sent.phone_code_hash not in blob
        finally:
            settings.tg_api_id, settings.tg_api_hash, settings.tg_session_string = old
            reset_login_runtime()
            session_login.CODE_WAIT_SECONDS = 15
            await engine.dispose()

    asyncio.run(run())


def test_persian_code_resend_and_live_check_hide_secrets():
    async def run():
        FakeClient.opened = []
        FakeClient.instances = []
        session_login.CODE_WAIT_SECONDS = 0
        set_client_opener(open_fake)
        engine, factory = _session()
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with factory() as db:
                await start_login(db, "12345", API_HASH, "۰۹۱۲۳۴۵۶۷۸۹")
                assert FakeClient.instances[0].calls[0] == ("send", NORMAL_PHONE)
                resent = await resend_login_code(db)
                _secrets_absent(resent)
                assert "hash-secret-resent-do-not-leak" not in json.dumps(resent)
                stored_hash = (await db.execute(select(SystemSetting).where(SystemSetting.key == "tg_login_hash"))).scalar_one()
                assert stored_hash.value == "hash-secret-resent-do-not-leak"
                ready = await submit_code(db, "۱۲۳۴۵")
                assert ready["step"] == "ready"
                _secrets_absent(ready)

                async def probe():
                    return {"authorized": True, "user_id": 77, "username": "checked", "premium": True}

                set_status_probe(probe)
                checked = await check_saved_session(db)
                assert checked["authorized"] is True
                assert checked["username"] == "checked"
                assert checked["premium"] is True
                _secrets_absent(checked)
        finally:
            reset_login_runtime()
            session_login.CODE_WAIT_SECONDS = 15
            await engine.dispose()

    asyncio.run(run())


def test_log_redacts_session_shaped_strings():
    secret = "1" + ("A" * 220)
    assert secret not in redact_secrets(f"leaked {secret}")
    assert "nvapi-" not in redact_secrets("key nvapi-abcdefghijklmnop")


def test_session_routes_are_owner_or_admin_only():
    from fastapi import HTTPException

    start_dep = inspect.signature(telegram_session_start).parameters["admin"].default.dependency
    code_dep = inspect.signature(telegram_session_code).parameters["admin"].default.dependency

    class Viewer:
        role = "VIEWER"

    class Owner:
        role = "OWNER"

    async def run():
        try:
            await start_dep(Viewer())
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError("viewer was allowed to start login")
        assert await code_dep(Owner()) is not None

    asyncio.run(run())
