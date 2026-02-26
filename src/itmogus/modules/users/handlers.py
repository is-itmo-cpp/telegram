from textwrap import dedent

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, User

from itmogus.modules.users.auth import get_role, is_owner
from itmogus.modules.users.repository import UserRepository
from itmogus.sheets.sheet import SheetsClient


router = Router()


async def _format_user_info(user: User, users: UserRepository) -> str:
    tag = f"@{user.username}" if user.username else "Не указан"
    role = (await get_role(user.id, users)).value

    info = dedent(
        f"""\
        Tag: {tag}
        Telegram ID: {user.id}
        Role: {role}
        """
    ).strip()

    registered = await users.get_user_by_telegram_id(user.id)
    if registered is not None:
        student = await users.get_student_by_isu(registered.isu)
        if student is not None:
            info += f"\nСтудент: {student.name} ({student.group})"

    return info


@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message):
    await message.answer("Привет! Для регистрации используй /register <ИСУ>.")


@router.message(Command("register"), F.chat.type == "private")
async def cmd_register(message: Message, sheets: SheetsClient):
    if (user := message.from_user) is None:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Использование: /register <ИСУ>")
        return

    isu_str = parts[1].strip()
    if not isu_str.isdigit():
        await message.answer("ИСУ должен быть числом.")
        return

    isu = int(isu_str)
    users = UserRepository(sheets)
    student = await users.register_user(user.id, isu)
    await message.answer(f"Вы успешно зарегистрированы, {student.name}.")


@router.message(Command("who"))
async def cmd_who(message: Message, sheets: SheetsClient):
    if (callee := message.from_user) is None:
        return

    target = None
    if (msg := message.reply_to_message) is not None:
        if (target := msg.from_user) is None:
            return

    if target is None:
        target = callee

    if target != callee and not is_owner(callee.id):
        return

    users = UserRepository(sheets)
    await message.answer(await _format_user_info(target, users))
