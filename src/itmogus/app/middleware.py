import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from itmogus.errors import BotError
from itmogus.modules.exam.errors import ExamConfigError
from itmogus.modules.users.errors import (
    IsuAlreadyBoundError,
    NoSuchIsuError,
    TelegramAlreadyBoundError,
)
from itmogus.sheets import (
    SheetNotFoundError,
    SheetsAPIError,
    SheetsAuthError,
    SheetsConnectionError,
    SheetsRateLimitError,
    SheetsSchemaError,
)


logger = logging.getLogger(__name__)

USER_MESSAGES = {
    SheetsConnectionError: "Ошибка подключения к Google. Попробуйте позже.",
    SheetsAuthError: "Нет доступа к таблице. Обратитесь к администратору.",
    SheetNotFoundError: "Таблица или лист не найден.",
    SheetsRateLimitError: "Слишком много запросов. Попробуйте позже.",
    SheetsAPIError: "Ошибка API Google.",
    SheetsSchemaError: "Неверная структура листа.",
    ExamConfigError: "Ошибка конфигурации экзамена.",
    TelegramAlreadyBoundError: "Этот Telegram уже привязан к другому ИСУ.",
    IsuAlreadyBoundError: "Этот ИСУ уже привязан к другому Telegram.",
    NoSuchIsuError: "Студент с таким ИСУ не найден.",
}


class ErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except BotError as e:
            base_message = USER_MESSAGES.get(type(e), "Произошла ошибка. Попробуйте позже.")

            if isinstance(e, SheetsSchemaError | ExamConfigError) and str(e):
                user_message = f"{base_message}\n\n{e}"
            else:
                user_message = base_message

            if isinstance(event, Message):
                await event.answer(user_message)
            elif isinstance(event, CallbackQuery):
                await event.answer(user_message, show_alert=True)

            logger.error("%s: %s", type(e).__name__, e)
            return
