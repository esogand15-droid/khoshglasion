import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.auth import clear_login_failures, login_is_blocked, note_login_failure
from backend.app.api.dashboard import dashboard
from backend.app.db.base import Base
from backend.app.models.message_log import MessageLog
import backend.app.models  # noqa: F401
from backend.app.api.preview import preview_ai_plan
from backend.app.api.system import webhook_secret_alert
from backend.app.formatting.emoji import EmojiMapping
from backend.app.formatting.richtext import prepare_post
from backend.app.formatting.textutil import utf16_len


def test_preview_refuses_locked_exam():
    should, decision, reason = preview_ai_plan("آزمون امروز\n1) الف\n2) ب", True, True)
    assert should is False
    assert decision["strategy"] == "preserve_strict"
    assert reason


def test_preview_allows_long_soft_text_only_when_ai_is_ready():
    text = "مشاوره " + ("سوال داوطلب را دقیق جواب بده و قدم بعدی را روشن کن. " * 30)
    blocked, decision, reason = preview_ai_plan(text, True, False)
    assert blocked is False
    assert decision["strategy"] == "light_edit"
    assert "آماده نیست" in (reason or "")
    allowed, _decision, empty = preview_ai_plan(text, True, True)
    assert allowed is True
    assert empty is None


def test_quote_and_option_emoji_are_not_swapped():
    text = "⭐ بیرون\n⭐ داخل نقل\n1) ⭐ گزینه"
    quote_at = text.index("⭐ داخل")
    entities = [{"type": "blockquote", "offset": utf16_len(text[:quote_at]), "length": utf16_len("⭐ داخل نقل")}]
    maps = [EmojiMapping("⭐", "999", enabled=True, priority=80)]
    updated, html, _entities, spans, _rules = prepare_post(
        text,
        raw_entities=entities,
        mappings=maps,
        enable_emoji=True,
        add_footer=False,
        add_divider=False,
        body_emoji=True,
    )
    assert "⭐ بیرون" in updated
    assert any(item[2] == "999" for item in spans)
    swapped = [updated[start:end] for start, end, _cid in spans]
    assert swapped == ["⭐"]
    assert "1) ⭐" in updated
    assert html and "999" in html
    assert html.count("999") == 1


def test_login_lock_counts_only_failures():
    ip = "test-lock-only-failures"
    clear_login_failures(ip)
    for _ in range(7):
        note_login_failure(ip)
    assert login_is_blocked(ip) is False
    note_login_failure(ip)
    assert login_is_blocked(ip) is True
    clear_login_failures(ip)
    assert login_is_blocked(ip) is False


def test_missing_webhook_secret_is_warned():
    assert webhook_secret_alert("")["level"] == "warn"
    assert webhook_secret_alert("already-set") is None


def test_dashboard_returns_real_failures():
    async def run():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            db.add(MessageLog(
                chat_id=-100, message_id=4, status="failed",
                error="edit_failed", category="exam", original_text="آزمون",
            ))
            await db.flush()
            data = await dashboard(db, admin=None)
            assert data["has_data"] is True
            assert data["failed"] == 1
            assert data["edited"] == 0
            assert data["failures"][0]["error"] == "edit_failed"
            assert data["failures"][0]["message_id"] == 4

    asyncio.run(run())
