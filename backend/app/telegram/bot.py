from aiogram import Bot
from aiogram.enums import ParseMode
from backend.app.core.config import get_settings
import logging
logger = logging.getLogger(__name__)

_bot: Bot | None = None

def get_bot() -> Bot | None:
    global _bot
    s = get_settings()
    if not s.bot_token:
        logger.warning("BOT_TOKEN not set")
        return None
    if _bot is None:
        _bot = Bot(token=s.bot_token)
    return _bot

async def close_bot():
    global _bot
    if _bot:
        await _bot.session.close()
        _bot = None
