import asyncio
import logging
from textwrap import dedent

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from itmogus.labs import resolve_lab_name
from itmogus.modules.sync.github import run_sync, SyncProgress
from itmogus.modules.users.auth import HasRole, Role
from itmogus.progress import render_progress_bar, run_with_progress


logger = logging.getLogger(__name__)
router = Router()


def _render_sync_progress(lab_name: str, progress: SyncProgress) -> str:
    if progress.total is None:
        return dedent(
            f"""\
            🔍 Собираю форки...

            🧪 Лабораторная: `{lab_name}`
            📊 Найдено: {progress.found}
            """
        ).strip()

    bar = render_progress_bar(progress.completed, progress.total)
    return dedent(
        f"""\
        🔄 Синхронизирую репозитории...

        🧪 Лабораторная: `{lab_name}`
        {bar} {progress.completed}/{progress.total}
        ✅ Успешно: {progress.success}
        ❌ Ошибки: {progress.failed}
        """
    ).strip()


@router.message(Command("sync"), HasRole(Role.TEAM))
async def cmd_sync(message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📝 Использование: /sync <lab>\n\nПример: /sync 6")
        return

    lab_name = resolve_lab_name(args[1])
    if lab_name is None:
        await message.answer("❌ Укажите положительное число или название (например: /sync 6, /sync livecoding2).")
        return

    progress = SyncProgress()
    status_msg = await message.answer(_render_sync_progress(lab_name, progress), parse_mode="Markdown")

    try:
        total, success, failed = await asyncio.wait_for(
            run_with_progress(
                status_msg,
                run_sync(lab_name, progress),
                lambda: _render_sync_progress(lab_name, progress),
                parse_mode="Markdown",
            ),
            timeout=600,
        )
    except asyncio.TimeoutError:
        logger.warning("Sync timed out for lab '%s'", lab_name)
        await status_msg.edit_text("⏱ Синхронизация превысила таймаут (10 минут)")
        return
    except Exception as e:
        logger.error("Sync failed for lab '%s': %s", lab_name, e)
        await status_msg.edit_text("❌ Ошибка при синхронизации. Попробуйте позже.")
        return

    logger.info("Synced forks for lab '%s': %d/%d success, %d failed", lab_name, success, total, failed)

    await status_msg.edit_text(
        dedent(
            f"""\
            ✅ Синхронизация завершена

            🧪 Лабораторная: `{lab_name}`
            📊 Всего: {total}
            ✅ Успешно: {success}
            ❌ Ошибки: {failed}
            """
        ).strip(),
        parse_mode="Markdown",
    )
