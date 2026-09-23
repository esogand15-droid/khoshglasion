import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.core.runtime import RuntimeState
from backend.app.db.base import Base
from backend.app.models import Channel, MessageLog  # noqa: F401
from backend.app.telegram.pipeline import content_hash, process_channel_post, reprocess_log


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


def test_no_change_stores_entities_for_retry():
    async def run():
        async with await _session() as db:
            db.add(Channel(
                chat_id=-100111,
                title="تست",
                enabled=True,
                auto_beautify=True,
                emoji_replacement=False,
                style_id="minimal",
                footer_text="",
                header_enabled=False,
            ))
            await db.flush()
            text = "سلام این متن متوسط است و فاصله اضافه ندارد"
            entities = [{"type": "bold", "offset": 0, "length": 4}]
            result = await process_channel_post(
                db, chat_id=-100111, message_id=9,
                text=text, caption=None, has_media=False, media_type="text",
                runtime=runtime(), entities=entities,
            )
            assert result["reason"] == "no_change"
            log = (await db.execute(select(MessageLog).where(MessageLog.id == result["log_id"]))).scalar_one()
            meta = json.loads(log.meta)
            assert meta["entities"] == entities
            assert meta["selection"]["structure_id"] == "locked"
            again = await reprocess_log(db, log, runtime())
            assert again["status"] in {"skipped", "dry_run"}

    asyncio.run(run())


def test_consecutive_soft_posts_do_not_repeat_structure():
    async def run():
        async with await _session() as db:
            db.add(Channel(chat_id=-100222, title="نرم", enabled=True, auto_beautify=True, emoji_replacement=False))
            await db.flush()
            text = "برنامه " + ("این بخش را دقیق و آرام بخوان. " * 8)
            state = runtime()
            first = await process_channel_post(
                db, chat_id=-100222, message_id=1,
                text=text, caption=None, has_media=False, media_type="text", runtime=state,
            )
            second = await process_channel_post(
                db, chat_id=-100222, message_id=2,
                text=text + " ادامه", caption=None, has_media=False, media_type="text", runtime=state,
            )
            assert first["status"] == "dry_run"
            assert second["status"] == "dry_run"
            rows = (await db.execute(select(MessageLog).order_by(MessageLog.message_id))).scalars().all()
            structures = [json.loads(row.meta)["selection"]["structure_id"] for row in rows]
            assert structures[0] != structures[1]
            assert any(item.startswith("template_id:") for item in first["applied"])

    asyncio.run(run())
