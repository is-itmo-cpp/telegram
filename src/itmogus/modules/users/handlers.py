from textwrap import dedent

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, User

from itmogus.modules.users.auth import Role, get_role, is_owner
from itmogus.modules.users.repository import UserRepository
from itmogus.sheets.sheet import SheetsClient


router = Router()


async def _format_user_info(user: User, users: UserRepository) -> str:
    tag = f"@{user.username}" if user.username else "Не указан"
    role = (await get_role(user.id, users)).value

    info = dedent(
        f"""\
        🏷 Tag: {tag}
        🆔 Telegram ID: {user.id}
        👤 Роль: {role}
        """
    ).strip()

    registered = await users.get_user_by_telegram_id(user.id)
    if registered is not None:
        student = await users.get_student_by_isu(registered.isu)
        if student is not None:
            info += f"\n📚 Студент: {student.name} ({student.group})"

    return info


@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message, sheets: SheetsClient):
    if (user := message.from_user) is None:
        return

    users = UserRepository(sheets)
    role = await get_role(user.id, users)

    commands = ["📝 /register <ИСУ> — регистрация"]

    if role in (Role.TEAM, Role.OWNER):
        commands.append("📋 /give <ИСУ> — выдать задачу")
        commands.append("📊 /exam — статус экзамена")
        commands.append("🔄 /sync <prefix> — синхронизация репозиториев")

    if role == Role.OWNER:
        commands.append("⚙️ /status — конфигурация бота")
        commands.append("📜 /logs — просмотр логов")
        commands.append("🔁 /reload — сброс кэша")
        commands.append("📌 /exam_tasks <url> — настроить таблицу билетов")
        commands.append("📝 /exam_logs <url> — настроить таблицу сдачи")
        commands.append("🧹 /exam_end — завершить экзамен")

    await message.answer("Доступные команды:\n\n" + "\n".join(commands))


@router.message(Command("register"), F.chat.type == "private")
async def cmd_register(message: Message, sheets: SheetsClient):
    if (user := message.from_user) is None:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("📝 Использование: /register <ИСУ>")
        return

    isu_str = parts[1].strip()
    if not isu_str.isdigit():
        await message.answer("❌ ИСУ должен быть числом.")
        return

    isu = int(isu_str)
    users = UserRepository(sheets)
    student = await users.register_user(user.id, isu)
    await message.answer(f"✅ Вы успешно зарегистрированы, {student.name}!")


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
