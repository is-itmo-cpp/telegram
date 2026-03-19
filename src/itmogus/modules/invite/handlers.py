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
