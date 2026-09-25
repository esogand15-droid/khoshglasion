import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from backend.app.core.secrets import peek

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_token: str = ""


def get_bot() -> Bot | None:
    global _bot, _token
    token = peek("bot_token")
    if not token:
        return None
    if _bot is None or _token != token:
        if _bot is not None:
            # Token rotated. The old session is closed on shutdown.
            _bot = None
        _token = token
        _bot = Bot(token=token, default=DefaultBotProperties(parse_mode=None))
    return _bot


async def close_bot() -> None:
    global _bot, _token
    if _bot is not None:
        try:
            await _bot.session.close()
        except Exception as exc:
            logger.warning("Bot session close failed: %s", exc)
        _bot = None
        _token = ""
