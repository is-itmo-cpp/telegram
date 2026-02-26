import asyncio
from textwrap import dedent

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from itmogus.modules.users.auth import HasRole, Role
from itmogus.modules.sync.github import run_sync


router = Router()


@router.message(Command("sync"), HasRole(Role.TEAM))
async def cmd_sync(message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("Использование: /sync <prefix>, например /sync labwork6")
        return

    prefix = args[1].strip()
    if not prefix.endswith("-"):
        prefix += "-"

    status_msg = await message.answer(
        f"Синхронизирую репозитории с префиксом `{prefix}`...",
        parse_mode="Markdown",
    )

    try:
        total, success, failed = await asyncio.wait_for(run_sync(prefix), timeout=600)

        await status_msg.edit_text(
            dedent(
                f"""\
                Синхронизация завершена!
                Префикс: {prefix}
                Всего репозиториев: {total}
                Успешно: {success}
                Ошибки: {failed}
                """
            ).strip()
        )
    except asyncio.TimeoutError:
        await status_msg.edit_text("Синхронизация превысила таймаут (10 минут)")
    except Exception as e:
        await status_msg.edit_text(f"Ошибка: {e}")
