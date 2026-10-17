from textwrap import dedent

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from itmogus.core.storage import Storage
from itmogus.modules.review.errors import ReviewConfigError
from itmogus.modules.review.models import get_queue_positions
from itmogus.modules.review.repository import ReviewRepository
from itmogus.modules.users.auth import HasRole, Role
from itmogus.modules.users.repository import UserRepository
from itmogus.result import Fail, Ok
from itmogus.sheets.sheet import SheetsClient


router = Router()

REVIEW_ERROR_MESSAGES = {
    ReviewConfigError.INVALID_URL: "❌ Не удалось распознать ссылку.",
    ReviewConfigError.SHEET_NOT_FOUND: "❌ Не удалось найти лист.",
    ReviewConfigError.SCHEMA_MISMATCH: "❌ Неверная структура листа.",
}


def _plural_works(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "работа"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "работы"
    return "работ"


def _format_position(position: int) -> str:
    ahead = position - 1
    if ahead == 0:
        return "Вы следующий. 😈🎉"
    return f"Перед вами {ahead} {_plural_works(ahead)}"


@router.message(Command("queue"), F.chat.type == "private")
async def cmd_queue(message: Message, sheets: SheetsClient, storage: Storage):
    if message.from_user is None:
        return

    reviews = ReviewRepository(sheets, storage)
    if not reviews.is_configured():
        await message.answer("⚠️ Таблица очереди на ревью не настроена. Обратитесь к преподавателю.")
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

    github_username = student.github.strip()
    if not github_username:
        await message.answer("❌ У вас не указан GitHub в профиле. Обратитесь к преподавателю.")
        return

    positions = get_queue_positions(await reviews.get_all_requests(), github_username)
    if not positions:
        await message.answer("✅ У вас нет работ в очереди на ревью.")
        return

    lines = [f"🧪 {p.lab}: {_format_position(p.position)}" for p in positions]
    await message.answer("📋 Очередь на ревью:\n\n" + "\n".join(lines))


@router.message(Command("queue_sheet"), HasRole(Role.OWNER))
async def cmd_queue_sheet(message: Message, sheets: SheetsClient, storage: Storage):
    reviews = ReviewRepository(sheets, storage)

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        sheet_name = reviews.get_requests_sheet_name()
        await message.answer(
            dedent(
                f"""\
                📋 Текущий лист очереди на ревью: {sheet_name or "не настроен"}

                📝 Использование: /queue_sheet <url>
                """
            ).strip()
        )
        return

    match await reviews.set_requests_sheet(args[1].strip()):
        case Fail(error):
            await message.answer(REVIEW_ERROR_MESSAGES[error])
        case Ok(sheet_name):
            await message.answer(f"✅ Таблица очереди на ревью установлена на лист '{sheet_name}'")
