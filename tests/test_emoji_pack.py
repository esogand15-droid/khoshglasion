import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.models.emoji import EmojiMapping
from backend.app.telegram.emoji_pack import (
    import_pack_names,
    is_safe_fallback,
    parse_pack_names,
    store_pack_stickers,
)
import backend.app.models  # noqa: F401


def test_pack_link_and_command_are_parsed():
    assert parse_pack_names("ببین https://t.me/addemoji/GoldLine_by_bot") == ["GoldLine_by_bot"]
    assert parse_pack_names("https://telegram.me/addstickers/Icons") == ["Icons"]
    assert parse_pack_names("/pack GoldLine_by_bot", allow_bare=True) == ["GoldLine_by_bot"]
    assert parse_pack_names("سلام GoldLine") == []


def test_font_fallback_is_rejected_and_emoji_is_kept():
    assert is_safe_fallback("🔥")
    assert is_safe_fallback("⚡️")
    assert is_safe_fallback("━")
    assert not is_safe_fallback("A")
    assert not is_safe_fallback("ا")
    assert not is_safe_fallback("1")
    assert not is_safe_fallback("سلام")


def test_pack_import_skips_letters_and_stores_emoji():
    async def run():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sticker_set = {
            "title": "نمونه",
            "sticker_type": "custom_emoji",
            "stickers": [
                {"emoji": "🔥", "custom_emoji_id": "100"},
                {"emoji": "A", "custom_emoji_id": "101"},
                {"emoji": "⚡", "custom_emoji_id": "102"},
            ],
        }
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            result = await store_pack_stickers(db, "Sample_by_bot", sticker_set)
            assert result["imported"] == 2
            assert result["unsafe"] == 1
            rows = (await db.execute(select(EmojiMapping))).scalars().all()
            by_id = {row.custom_emoji_id: row for row in rows}
            assert "101" not in by_id
            assert by_id["102"].category == "divider"
            assert by_id["100"].category is None
            again = await store_pack_stickers(db, "Sample_by_bot", sticker_set)
            assert again["imported"] == 0
            assert again["duplicate"] == 2

    asyncio.run(run())


def test_import_report_uses_injected_fetch():
    async def run():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async def fetch(name: str):
            assert name == "Icons"
            return {"title": "Icons", "sticker_type": "custom_emoji", "stickers": [{"emoji": "⭐", "custom_emoji_id": "9"}]}

        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            result = await import_pack_names(db, ["Icons"], fetch)
            assert result["imported"] == 1
            assert "Icons" in result["message"]

    asyncio.run(run())
