import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from itmogus.modules.invite.errors import InviteError
from itmogus.modules.invite.github import ensure_invitation
from itmogus.modules.users.repository import UserRepository
from itmogus.result import Fail, Ok
from itmogus.sheets.sheet import SheetsClient


logger = logging.getLogger(__name__)


router = Router()

INVITE_ERROR_MESSAGES = {
    InviteError.NOT_REGISTERED: "❌ Вы не зарегистрированы. Используйте /register <ИСУ>",
    InviteError.NO_GITHUB: "❌ У вас не указан GitHub в профиле. Обратитесь к преподавателю.",
    InviteError.ALREADY_HAS_ACCESS: "✅ Вы уже имеете доступ к репозиторию.",
    InviteError.TEMPLATE_NOT_FOUND: "❌ Шаблон репозитория не найден. Обратитесь к преподавателю.",
    InviteError.TEMPLATE_NOT_PRIVATE: "❌ Шаблон репозитория должен быть приватным. Обратитесь к преподавателю.",
    InviteError.FORK_FAILED: "❌ Не удалось создать репозиторий. Попробуйте позже.",
}


class InviteState(StatesGroup):
    waiting_for_lab_number = State()


@router.message(Command("invite"), F.chat.type == "private")
async def cmd_invite(message: Message, state: FSMContext, sheets: SheetsClient):
    if message.from_user is None:
        return

    users = UserRepository(sheets)

    bot_user = await users.get_user_by_telegram_id(message.from_user.id)
    if bot_user is None:
        await message.answer(INVITE_ERROR_MESSAGES[InviteError.NOT_REGISTERED])
        return

    student = await users.get_student_by_isu(bot_user.isu)
    if student is None:
        await message.answer(INVITE_ERROR_MESSAGES[InviteError.NOT_REGISTERED])
        return

    if not student.github:
        await message.answer(INVITE_ERROR_MESSAGES[InviteError.NO_GITHUB])
        return

    await state.update_data(github_username=student.github)
    await state.set_state(InviteState.waiting_for_lab_number)
    await message.answer("📝 Введите номер лабораторной работы, к которой у вас нету доступа:")


@router.message(InviteState.waiting_for_lab_number)
async def process_lab_number(message: Message, state: FSMContext):
    if message.text is None:
        return

    data = await state.get_data()
    await state.clear()

    github_username = data["github_username"]

    lab_str = message.text.strip()
    if not lab_str.isdigit() or int(lab_str) < 1:
        await message.answer("❌ Номер должен быть положительным целым числом.")
        return

    lab_number = int(lab_str)

    result = await ensure_invitation(lab_number, github_username)

    match result:
        case Ok((invitation, True)):
            await message.answer(f"✅ Приглашение отправлено: {invitation.html_url}")
        case Ok((invitation, False)):
            await message.answer(f"📧 У вас уже есть активное приглашение: {invitation.html_url}")
        case Fail(error):
            await message.answer(INVITE_ERROR_MESSAGES[error])
