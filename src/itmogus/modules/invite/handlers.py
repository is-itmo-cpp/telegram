import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from itmogus.modules.invite.errors import InviteError
from itmogus.modules.invite.github import ensure_invitation, EnsureStatus
from itmogus.modules.users.repository import UserRepository
from itmogus.result import Fail, Ok
from itmogus.sheets.sheet import SheetsClient


logger = logging.getLogger(__name__)


router = Router()


class InviteState(StatesGroup):
    waiting_for_lab_number = State()


ALLOWED_TEMPLATE_NAMES = {"livecoding2"}


def _resolve_template_name(user_input: str) -> str | None:
    if user_input.isdigit():
        num = int(user_input)
        if num < 1:
            return None
        return f"labwork{num}"
    if user_input in ALLOWED_TEMPLATE_NAMES:
        return user_input
    return None


@router.message(Command("invite"), F.chat.type == "private")
async def cmd_invite(message: Message, state: FSMContext, sheets: SheetsClient):
    if message.from_user is None:
        return

    users = UserRepository(sheets)

    bot_user = await users.get_user_by_telegram_id(message.from_user.id)
    if bot_user is None:
        await message.answer("❌ Вы не зарегистрированы. Используйте /register <ИСУ>")
        return

    student = await users.get_student_by_isu(bot_user.isu)
    if student is None:
        await message.answer("❌ Вы не зарегистрированы. Используйте /register <ИСУ>")
        return

    if not student.github:
        await message.answer("❌ У вас не указан GitHub в профиле. Обратитесь к преподавателю.")
        return

    await state.update_data(github_username=student.github)
    await state.set_state(InviteState.waiting_for_lab_number)
    await message.answer("📝 Введите номер или название лабораторной работы (например: 1 или livecoding2):")


@router.message(InviteState.waiting_for_lab_number)
async def process_lab_number(message: Message, state: FSMContext):
    if message.text is None:
        return

    data = await state.get_data()
    await state.clear()

    github_username = data["github_username"]

    lab_str = message.text.strip()
    template_name = _resolve_template_name(lab_str)
    if template_name is None:
        await message.answer("❌ Введите положительное число или название (например: 1, livecoding2).")
        return

    result = await ensure_invitation(template_name, github_username)

    match result:
        case Ok(EnsureStatus.InvitationCreated(invitation)):
            await message.answer(f"📧 Приглашение отправлено: {invitation.html_url}")
        case Ok(EnsureStatus.InvitationExists(invitation)):
            await message.answer(f"📧 У вас уже есть активное приглашение: {invitation.html_url}")
        case Ok(EnsureStatus.RepoExists(url)):
            await message.answer(f"✅ Вы уже имеете доступ к репозиторию: {url}.")
        case Fail(InviteError.TEMPLATE_NOT_FOUND):
            await message.answer("❌ Шаблон репозитория не найден. Обратитесь к преподавателю.")
        case Fail(InviteError.TEMPLATE_NOT_PRIVATE):
            await message.answer("❌ Шаблон репозитория должен быть приватным. Обратитесь к преподавателю.")
        case Fail(InviteError.FORK_FAILED):
            await message.answer("❌ Не удалось создать репозиторий. Попробуйте позже.")
        case Fail(error):
            await message.answer(f"❌ Произошла ошибка: {error}.")
