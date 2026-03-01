import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from itmogus.app.middleware import ErrorMiddleware
from itmogus.core.config import config
from itmogus.core.storage import Storage
from itmogus.logging import ContextMiddleware, setup_logging
from itmogus.modules.admin import router as admin_router
from itmogus.modules.exam import router as exam_router
from itmogus.modules.sync import router as sync_router
from itmogus.modules.users import router as users_router
from itmogus.sheets.sheet import SheetsClient


logger = logging.getLogger(__name__)


async def main():
    setup_logging()

    sheets_client = await SheetsClient.create(config.google_credentials_path)
    state = Storage(Path(config.storage_dir))

    bot = Bot(token=config.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp.workflow_data["sheets"] = sheets_client
    dp.workflow_data["storage"] = state

    dp.message.middleware(ContextMiddleware())
    dp.callback_query.middleware(ContextMiddleware())
    dp.message.middleware(ErrorMiddleware())
    dp.callback_query.middleware(ErrorMiddleware())

    dp.include_router(users_router)
    dp.include_router(exam_router)
    dp.include_router(sync_router)
    dp.include_router(admin_router)

    logger.info("Bot started")

    try:
        await dp.start_polling(bot)
    finally:
        await sheets_client.close()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
