import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.core.runtime import RuntimeState
from backend.app.db.base import Base
from backend.app.models import Channel, MessageLog  # noqa: F401
from backend.app.telegram.pipeline import content_hash, process_channel_post


def runtime(**overrides) -> RuntimeState:
    values = dict(
        dry_run=True,
        kill_switch=False,
        safe_mode=True,
        ai_enabled=False,
        ai_base_url="",
        ai_model="",
        ai_api_key="",
        ai_temperature=0.7,
        ai_max_tokens=200,
        ai_min_chars=40,
        edit_delay_seconds=0,
        auto_register_channels=False,
        reprocess_edits=True,
        persian_normalize=False,
        max_emoji_per_post=8,
        preserve_links=True,
        notify_chat_id="",
        admin_telegram_ids="",
        premium_mode="off",
        default_footer="",
    )
    values.update(overrides)
    return RuntimeState(**values)


async def _session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)()


def test_unknown_channel_does_not_crash_before_hash():
    async def run():
        async with await _session() as db:
            result = await process_channel_post(
                db, chat_id=-1001234567890, message_id=7,
                text="اطلاعیه آزمون", caption=None, has_media=False, media_type="text",
                runtime=runtime(auto_register_channels=False),
            )
            assert result["status"] == "skipped"
            assert result["reason"] == "unknown_channel"
            await db.commit()

    asyncio.run(run())


def test_auto_register_then_idempotent_skip():
    async def run():
        async with await _session() as db:
            state = runtime(auto_register_channels=True, dry_run=True)
            first = await process_channel_post(
                db, chat_id=-1009876543210, message_id=3,
                text="برنامه هفته آینده آماده است و باید دقیق خوانده شود",
                caption=None, has_media=False, media_type="text", runtime=state,
            )
            assert first["status"] in {"dry_run", "skipped"}
            second = await process_channel_post(
                db, chat_id=-1009876543210, message_id=3,
                text="برنامه هفته آینده آماده است و باید دقیق خوانده شود",
                caption=None, has_media=False, media_type="text", runtime=state,
            )
            assert second["reason"] == "idempotent_duplicate"
            assert content_hash("abc") == content_hash("abc")

    asyncio.run(run())
