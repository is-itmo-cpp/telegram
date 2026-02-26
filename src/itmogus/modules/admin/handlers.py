from textwrap import dedent

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from itmogus.core.config import config
from itmogus.modules.users.auth import HasRole, Role
from itmogus.sheets.sheet import SheetsClient


router = Router()


@router.message(Command("reload"), HasRole(Role.OWNER))
async def cmd_reload(message: Message, sheets: SheetsClient):
    sheets.invalidate_all_sheets()
    await message.answer("Кэш сброшен.")


@router.message(Command("status"), HasRole(Role.OWNER))
async def cmd_status(message: Message, sheets: SheetsClient):
    if not config.users_table_id:
        await message.answer("Users table не настроена.")
        return

    async def _link(sheet_name: str) -> str:
        gid = await sheets.resolve_sheet_gid(config.users_table_id, sheet_name)
        url = f"https://docs.google.com/spreadsheets/d/{config.users_table_id}/edit#gid={gid}"
        return f"[{sheet_name}]({url})"

    students_link = await _link("Students")
    users_link = await _link("Users")
    permissions_link = await _link("Team")

    await message.answer(
        dedent(
            f"""\
            ⚙️ Текущая конфигурация:

            - Лист прав: {permissions_link}
            - Лист регистраций: {users_link}
            - Лист студентов: {students_link}
            - Github org: `{config.github_org}`
            """
        ).strip(),
        parse_mode="Markdown",
    )
