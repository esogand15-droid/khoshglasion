import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from backend.app.core.runtime import RuntimeState
from backend.app.telegram.bot import get_bot

logger = logging.getLogger(__name__)


async def notify(runtime: RuntimeState, text: str, chat_id: int | None = None, message_id: int | None = None) -> None:
    target = runtime.notify_id
    if not target:
        return
    bot = get_bot()
    if not bot:
        return
    markup = None
    if chat_id and message_id:
        token = f"retry:{chat_id}:{message_id}"
        if len(token.encode("utf-8")) <= 64:
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="تلاش دوباره", callback_data=token)
            ]])
    try:
        await bot.send_message(target, text[:3900], reply_markup=markup)
    except Exception as exc:
        logger.warning("Admin notification failed: %s", exc)
