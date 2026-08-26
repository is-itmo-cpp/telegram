import asyncio
import logging
from textwrap import dedent

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from itmogus.modules.sync.github import run_sync, SyncProgress
from itmogus.modules.users.auth import HasRole, Role
from itmogus.progress import render_progress_bar, run_with_progress


logger = logging.getLogger(__name__)
router = Router()


def _render_sync_progress(prefix: str, progress: SyncProgress) -> str:
    if progress.total is None:
        return dedent(
            f"""\
            🔍 Ищу репозитории...

            📂 Префикс: `{prefix}`
            🔎 Проверено: {progress.scanned}
            📊 Найдено: {progress.found}
            """
        ).strip()

    bar = render_progress_bar(progress.completed, progress.total)
    return dedent(
        f"""\
        🔄 Синхронизирую репозитории...

        📂 Префикс: `{prefix}`
        {bar} {progress.completed}/{progress.total}
        ✅ Успешно: {progress.success}
        ❌ Ошибки: {progress.failed}
        """
    ).strip()


@router.message(Command("sync"), HasRole(Role.TEAM))
async def cmd_sync(message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("📝 Использование: /sync <prefix>\n\nПример: /sync labwork6")
        return

    prefix = args[1].strip()
    if not prefix.endswith("-"):
        prefix += "-"

    progress = SyncProgress()
    status_msg = await message.answer(_render_sync_progress(prefix, progress), parse_mode="Markdown")

    try:
        total, success, failed = await asyncio.wait_for(
            run_with_progress(
                status_msg,
                run_sync(prefix, progress),
                lambda: _render_sync_progress(prefix, progress),
                parse_mode="Markdown",
            ),
            timeout=600,
        )
    except asyncio.TimeoutError:
        logger.warning("Sync timed out for prefix '%s'", prefix)
        await status_msg.edit_text("⏱ Синхронизация превысила таймаут (10 минут)")
        return
    except Exception as e:
        logger.error("Sync failed for prefix '%s': %s", prefix, e)
        await status_msg.edit_text("❌ Ошибка при синхронизации. Попробуйте позже.")
        return

    logger.info("Synced repos with prefix '%s': %d/%d success, %d failed", prefix, success, total, failed)

    await status_msg.edit_text(
        dedent(
            f"""\
            ✅ Синхронизация завершена

            📂 Префикс: `{prefix}`
            📊 Всего: {total}
            ✅ Успешно: {success}
            ❌ Ошибки: {failed}
            """
        ).strip(),
        parse_mode="Markdown",
    )
