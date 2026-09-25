import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.content.pipeline import (
    choose_hashtags,
    extra_long_numbers,
    merge_analysis,
    pick_angle,
    too_similar,
)
from backend.app.content.prompts import PROMPTS
from backend.app.content.publish import prepare_publish_payload
from backend.app.content.schedule import allow_publish, cursor_after, oldest_unread, retry_delay_seconds
from backend.app.db.base import Base
from backend.app.formatting.emoji import EmojiMapping
from backend.app.models.automation import AutomationConfig, DraftPost, NewsSource
from backend.app.services.autopost import remember_version
import backend.app.models  # noqa: F401


def test_pages_do_not_skip_the_middle():
    messages = [{"id": index, "text": "x"} for index in range(1, 13)]
    first, more = oldest_unread(messages, 0, 5)
    assert [item["id"] for item in first] == [1, 2, 3, 4, 5]
    assert more is True
    cursor = cursor_after(0, first, {item["id"] for item in first})
    second, still = oldest_unread(messages, cursor, 5)
    assert [item["id"] for item in second] == [6, 7, 8, 9, 10]
    assert still is True
    assert cursor_after(0, first, {1, 3}) == 1


def test_not_ready_does_not_pass_the_current_message():
    page = [{"id": 4, "usable": False}, {"id": 5, "usable": True}, {"id": 6, "usable": True}]
    assert cursor_after(3, page, {4}, stop_before=5) == 4


def test_near_copy_is_more_than_the_opening_line():
    shared = "جزئیات ثبت نام همان اطلاعیه رسمی است و ظرفیت اعلام‌شده تغییر نکرده است و مهلت تمدید شده."
    first = "سازمان سنجش امروز خبر داد.\n" + shared
    second = "یک شروع کاملاً متفاوت اینجاست.\n" + shared
    assert too_similar(first, [second]) is True
    assert too_similar("این یک یادداشت کوتاه دیگر است", [first]) is False


def test_disabled_hashtag_is_not_forced():
    tags = choose_hashtags("news", "اطلاعیه ثبت نام", enabled={"اطلاعیه"}, forbidden=set())
    assert "خبر" not in tags
    assert tags == ["اطلاعیه"]


def test_analysis_rejects_an_invented_number():
    source = "مهلت ثبت نام تمدید شد."
    merged = merge_analysis(
        {"confidence": "medium", "reasons": [], "category": "news"},
        {"summary": "مهلت تا ۱۴۰۴۱۲۳۴ تمدید شد", "category": "news", "confidence": "high"},
        source,
    )
    assert merged["confidence"] == "low"
    assert extra_long_numbers(source, "ظرفیت ۹۹۹ نفر اضافه شد") == ["999"]


def test_angle_rotates_away_from_the_last_one():
    key, _label = pick_angle(["news_short"])
    assert key != "news_short"


def test_daily_cap_and_category_balance():
    assert allow_publish("news", {}, {"news", "consulting"}, 4, True) is True
    assert allow_publish("news", {"news": 1}, {"news", "consulting"}, 4, True) is False
    assert allow_publish("consulting", {"news": 1}, {"news", "consulting"}, 4, True) is True
    assert allow_publish("consulting", {"news": 2, "consulting": 2}, {"news", "consulting"}, 4, True) is False


def test_retry_delay_backs_off():
    assert retry_delay_seconds(1) == 60
    assert retry_delay_seconds(2) == 120
    assert retry_delay_seconds(8) == 900


def test_publish_render_uses_only_library_emoji_and_the_body():
    maps = [
        EmojiMapping("📢", "101", enabled=True, priority=90),
        EmojiMapping("✨", "102", enabled=True, priority=70),
    ]
    body = "\n".join([
        "اطلاعیه مهم ثبت نام",
        "مدارس این هفته کلاس حضوری ندارند و برنامه جایگزین اعلام شد.",
        "دانش‌آموزان باید برنامه را از مدرسه خود بگیرند.",
        "مهلت ارسال فرم تا پایان هفته است.",
        "جزئیات در پیام مدرسه آمده است.",
    ])
    payload = prepare_publish_payload(body, "announcement", "list", maps)
    assert payload["emoji_ids"]
    assert set(payload["emoji_ids"]) <= {"101", "102"}
    assert all(item.isdigit() for item in payload["emoji_ids"])
    marked = [line for line in payload["text"].splitlines() if line.startswith(("📢", "✨"))]
    assert len(marked) >= 2


def test_prompts_are_separate_stages():
    assert len({PROMPTS["analyzer"], PROMPTS["generator"], PROMPTS["validator"]}) == 3
    assert "JSON" in PROMPTS["analyzer"]
    assert "SKIP" in PROMPTS["generator"]
    assert "REVIEW" in PROMPTS["validator"]


def test_edit_never_overwrites_source_text():
    draft = DraftPost(body="نسخه اول که کافی بلند است", source_content="متن اصلی منبع", version=1)
    remember_version(draft, "نسخه ویرایش‌شده که هنوز واقعیت را نگه داشته است", "edit")
    assert draft.source_content == "متن اصلی منبع"
    assert draft.body.startswith("نسخه ویرایش")
    assert draft.version == 2


def test_collect_reads_the_next_page_instead_of_skipping_it():
    messages = [
        {
            "id": index,
            "text": f"اطلاعیه شماره {index}: مهلت ثبت نام این نوبت تمدید شد و جزئیات تازه از سوی مدرسه اعلام گردید.",
            "title": "news",
            "date": None,
            "usable": True,
        }
        for index in range(1, 13)
    ]

    async def run():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async def fake_read(username, min_id=0, limit=40):
            page, truncated = oldest_unread(messages, min_id, 5)
            return page, None, truncated

        async def fake_runtime(_db):
            class Ready:
                ai_ready = True
            return Ready()

        async def fake_analyze(_db, text, created_at, runtime):
            return {"category": "news", "value": "USEFUL", "importance": "normal", "confidence": "medium", "reasons": [], "summary": "خلاصه منبع"}

        async def fake_draft(text, label, runtime, **kwargs):
            return (f"بازنویسی مستقل درباره {text[:24]} برای کانال مشاوره، بدون کپی جمله.", "news", "ok")

        async def fake_validate(_db, source, body, runtime):
            return True

        from backend.app.services import automation_runner as runner
        original = (runner.read_channel_posts, runner.load_runtime, runner._analyze, runner.draft_from_source, runner._validate)
        runner.read_channel_posts = fake_read
        runner.load_runtime = fake_runtime
        runner._analyze = fake_analyze
        runner.draft_from_source = fake_draft
        runner._validate = fake_validate
        try:
            await _collect_pages(factory, runner)
        finally:
            (
                runner.read_channel_posts,
                runner.load_runtime,
                runner._analyze,
                runner.draft_from_source,
                runner._validate,
            ) = original

    async def _collect_pages(factory, runner):
        async with factory() as db:
            db.add(AutomationConfig(enabled=True, auto_publish=False))
            db.add(NewsSource(username="konkur_news", last_message_id=0))
            await db.commit()
            first = await runner.collect_sources(db, force=True)
            await db.commit()
            source = (await db.execute(__import__("sqlalchemy").select(NewsSource))).scalar_one()
            assert first["created"] == 5
            assert first["truncated"] is True
            assert int(source.last_message_id) == 5
            second = await runner.collect_sources(db, force=True)
            await db.commit()
            await db.refresh(source)
            assert second["created"] == 5
            assert int(source.last_message_id) == 10
            stored = (await db.execute(__import__("sqlalchemy").select(DraftPost))).scalars().all()
            assert all(row.source_content and row.source_content != row.body for row in stored)

    asyncio.run(run())
