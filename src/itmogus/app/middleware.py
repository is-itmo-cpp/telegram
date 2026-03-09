import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from itmogus.errors import BotError


logger = logging.getLogger(__name__)


class ErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except BotError as e:
            message = e.user_message
            if str(e):
                message = f"{message}\n\n{e}"

            if isinstance(event, Message):
                await event.answer(message)
            elif isinstance(event, CallbackQuery):
                await event.answer(message, show_alert=True)

            logger.error("%s: %s", type(e).__name__, e)
            return
