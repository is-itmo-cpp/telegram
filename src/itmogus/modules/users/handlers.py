from dataclasses import dataclass
from textwrap import dedent
from typing import TypeGuard

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User

from itmogus.core.actions import CANCEL, CONFIRM, Action, PendingActions, action_button
from itmogus.modules.users.auth import Role, get_role, is_owner
from itmogus.modules.users.repository import RegisterError, UserRepository
from itmogus.result import Fail, Ok
from itmogus.sheets.sheet import SheetsClient


router = Router()


@dataclass(frozen=True)
class RegisterPayload:
    isu: int


def is_accessible_message(msg) -> TypeGuard[Message]:
    return isinstance(msg, Message)


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

    commands = [
        "📝 /register <ИСУ> — регистрация",
        "📧 /invite <lab> — получение доступа к репозиторию",
    ]

    if role in (Role.TEAM, Role.OWNER):
        commands.append("📋 /give <ИСУ> — выдать задачу")
        commands.append("📊 /exam — статус экзамена")
        commands.append("🔄 /sync <lab> — синхронизация репозиториев")
        commands.append("🚀 /rollout <lab> — создать репозитории для студентов")

    if role == Role.OWNER:
        commands.append("⚙️ /status — конфигурация бота")
        commands.append("📜 /logs — просмотр логов")
        commands.append("🔁 /reload — сброс кэша")
        commands.append("📌 /exam_tasks <url> — настроить таблицу билетов")
        commands.append("📝 /exam_logs <url> — настроить таблицу сдачи")
        commands.append("🧹 /exam_end — завершить экзамен")

    await message.answer("Доступные команды:\n\n" + "\n".join(commands))


@router.message(Command("register"), F.chat.type == "private")
async def cmd_register(message: Message, sheets: SheetsClient, actions: PendingActions):
    if message.from_user is None:
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

    existing = await users.get_user_by_telegram_id(message.from_user.id)
    if existing is not None:
        student = await users.get_student_by_isu(existing.isu)
        name = student.name if student else f"ИСУ {existing.isu}"
        await message.answer(f"❌ Вы уже зарегистрированы как {name}.")
        return

    student = await users.get_student_by_isu(isu)
    if student is None:
        await message.answer("❌ Студент с таким ИСУ не найден.")
        return

    token = actions.create(owner_id=message.from_user.id, payload=RegisterPayload(isu=isu))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                action_button("✅", token, CONFIRM),
                action_button("❌", token, CANCEL),
            ]
        ]
    )
    await message.answer(
        f"Вы хотите зарегистрироваться как {student.name} ({student.group})?",
        reply_markup=keyboard,
    )


@router.callback_query(Action(RegisterPayload))
async def callback_register(
    callback: CallbackQuery,
    payload: RegisterPayload,
    choice: str,
    sheets: SheetsClient,
):
    if choice != CONFIRM:
        if is_accessible_message(callback.message):
            await callback.message.edit_text("❌ Регистрация отменена.")
        await callback.answer()
        return

    users = UserRepository(sheets)
    error_messages = {
        RegisterError.TELEGRAM_ALREADY_BOUND: "❌ Этот Telegram уже привязан к другому ИСУ.",
        RegisterError.ISU_ALREADY_BOUND: "❌ Этот ИСУ уже привязан к другому Telegram.",
        RegisterError.NO_SUCH_ISU: "❌ Студент с таким ИСУ не найден.",
    }

    match await users.register_user(callback.from_user.id, payload.isu):
        case Fail(error):
            if is_accessible_message(callback.message):
                await callback.message.edit_text(error_messages[error])
            await callback.answer()
        case Ok(student):
            if is_accessible_message(callback.message):
                await callback.message.edit_text(f"✅ Вы успешно зарегистрированы, {student.name}!")
            await callback.answer()


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
