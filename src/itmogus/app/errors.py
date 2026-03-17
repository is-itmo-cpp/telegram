import logging

from aiogram import Dispatcher
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent

from itmogus.errors import InfraError
from itmogus.logging import current_event_id


logger = logging.getLogger(__name__)


def setup_error_handlers(dp: Dispatcher) -> None:
    @dp.error(ExceptionTypeFilter(InfraError))
    async def handle_infra_error(event: ErrorEvent):
        e = event.exception
        assert isinstance(e, InfraError)

        update = event.update
        if update.message:
            await update.message.answer(e.user_message)
        elif update.callback_query:
            await update.callback_query.answer(e.user_message, show_alert=True)

        logger.error("%s: %s", type(e).__name__, e)

    @dp.error()
    async def handle_unexpected_error(event: ErrorEvent):
        e = event.exception
        event_id = current_event_id.get()
        logger.critical("Unexpected error: %s", e, exc_info=True)

        error_ref = f" (trace: `{event_id[:8]}`)" if event_id else ""
        user_message = f"Произошла непредвиденная ошибка{error_ref}. Попробуйте позже."

        update = event.update
        if update.message:
            await update.message.answer(user_message, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.answer(user_message, show_alert=True)
