import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from itmogus.labs import resolve_lab_name
from itmogus.modules.invite.errors import InviteError
from itmogus.modules.invite.github import ensure_invitation, EnsureStatus
from itmogus.modules.users.repository import UserRepository
from itmogus.result import Fail, Ok
from itmogus.sheets.sheet import SheetsClient


logger = logging.getLogger(__name__)


router = Router()


@router.message(Command("invite"), F.chat.type == "private")
async def cmd_invite(message: Message, sheets: SheetsClient):
    if message.from_user is None:
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📝 Использование: /invite <lab>\n\nПример: /invite 1")
        return

    template_name = resolve_lab_name(args[1])
    if template_name is None:
        await message.answer("❌ Укажите положительное число или название (например: /invite 1, /invite livecoding2).")
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

    result = await ensure_invitation(template_name, student.github)

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
