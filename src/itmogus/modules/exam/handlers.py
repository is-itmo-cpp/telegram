import logging
from datetime import datetime
from textwrap import dedent
from typing import TypeGuard
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.exceptions import AiogramError
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from itmogus.core.storage import Storage
from itmogus.modules.exam.errors import ExamConfigError
from itmogus.modules.exam.repository import ExamRepository
from itmogus.modules.users.auth import HasRole, Role
from itmogus.modules.users.repository import UserRepository
from itmogus.result import Fail, Ok
from itmogus.sheets.sheet import SheetsClient


logger = logging.getLogger(__name__)

router = Router()
TIMEZONE = ZoneInfo("Europe/Moscow")

EXAM_ERROR_MESSAGES = {
    ExamConfigError.INVALID_URL: "❌ Не удалось распознать ссылку.",
    ExamConfigError.SHEET_NOT_FOUND: "❌ Не удалось найти лист.",
    ExamConfigError.SCHEMA_MISMATCH: "❌ Неверная структура листа.",
    ExamConfigError.NOT_CONFIGURED: "❌ Экзамен не настроен.",
}


class TaskCallback(CallbackData, prefix="task"):
    task_id: str


def is_accessible_message(msg) -> TypeGuard[Message]:
    return isinstance(msg, Message)


async def get_tasks_keyboard(exams: ExamRepository) -> InlineKeyboardMarkup:
    tasks = await exams.get_all_tasks()
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{task.name} ({task.points})",
                callback_data=TaskCallback(task_id=task.id).pack(),
            )
        ]
        for task in tasks.values()
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("give"), HasRole(Role.TEAM))
async def cmd_give(message: Message, state: FSMContext, sheets: SheetsClient, storage: Storage):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📝 Использование: /give <ИСУ>")
        return

    isu_str = args[1].strip()
    if not isu_str.isdigit():
        await message.answer("❌ Неверный формат ИСУ.\n\n📝 Использование: /give <ИСУ>")
        return

    exams = ExamRepository(sheets, storage)
    match exams.check_configured():
        case Fail(error):
            await message.answer(EXAM_ERROR_MESSAGES[error])
            return
        case Ok():
            pass

    users = UserRepository(sheets)
    student = await users.get_student_by_isu(int(isu_str))
    if not student:
        await message.answer(f"❌ Студент с ИСУ {isu_str} не найден.")
        return

    registered_user = await users.get_user_by_isu(student.isu)
    header = "🎓 Студент найден" if registered_user else "⚠️ Студент не зарегистрирован в Telegram"

    keyboard = await get_tasks_keyboard(exams)
    await state.update_data(student_isu=student.isu, student_name=student.name, student_group=student.group)
    await message.answer(
        dedent(
            f"""\
            {header}

            👤 {student.name}
            🆔 ИСУ: {student.isu}
            📚 Группа: {student.group}

            Выберите задачу:
            """
        ).strip(),
        reply_markup=keyboard,
    )


@router.callback_query(TaskCallback.filter())
async def callback_select_task(
    callback: CallbackQuery,
    callback_data: TaskCallback,
    state: FSMContext,
    sheets: SheetsClient,
    storage: Storage,
):
    data = await state.get_data()
    student_isu = data.get("student_isu")
    student_name = data.get("student_name")
    student_group = data.get("student_group", "")

    if not student_isu or not student_name:
        await callback.answer("Ошибка: данные выдачи потеряны")
        return

    exams = ExamRepository(sheets, storage)
    all_tasks = await exams.get_all_tasks()
    task = all_tasks.get(callback_data.task_id)
    if not task:
        await callback.answer("Задача не найдена")
        return

    timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    await exams.log_exam(student_isu, student_group, student_name, task.id, task.points, timestamp)

    delivery_error = False
    users = UserRepository(sheets)
    recipient = await users.get_user_by_isu(student_isu)
    if recipient and callback.bot:
        try:
            await callback.bot.send_message(
                recipient.telegram_id,
                f"Вам выдано задание:\n\n```cpp\n{task.text}\n```\nЖелаем удачи!",
                parse_mode="Markdown",
            )
        except AiogramError:
            logger.exception("Failed to send task to user telegram_id=%d, ISU=%d", recipient.telegram_id, recipient.isu)
            delivery_error = True
    else:
        logger.error("Failed to send task to user ISU=%d", student_isu)
        delivery_error = True

    if is_accessible_message(callback.message):
        text = dedent(
            f"""\
            ✅ Студенту выдана задача

            👤 Студент: {student_name}
            🆔 ИСУ: {student_isu}
            📋 Задача: {task.name}
            💯 Баллы: {task.points}
            🕐 Время: {timestamp}
            """
        ).strip()
        if delivery_error:
            text += "\n\n⚠️ Не удалось отправить задачу студенту в Telegram."
        await callback.message.edit_text(text)

    await callback.answer()
    await state.clear()


@router.callback_query(lambda c: c.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    if is_accessible_message(callback.message):
        await callback.message.edit_text("❌ Отменено")
    await callback.answer()
    await state.clear()


@router.message(Command("exam_tasks"), HasRole(Role.OWNER))
async def cmd_exam_tasks(message: Message, sheets: SheetsClient, storage: Storage):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        exams = ExamRepository(sheets, storage)
        tasks_name = await exams.get_tasks_sheet_name()
        await message.answer(
            dedent(
                f"""\
                📋 Текущий лист билетов: {tasks_name or "не настроен"}

                📝 Использование: /exam_tasks <url>
                """
            ).strip()
        )
        return

    exams = ExamRepository(sheets, storage)
    match await exams.set_exam_tasks(args[1].strip()):
        case Fail(error):
            await message.answer(EXAM_ERROR_MESSAGES[error])
        case Ok(sheet_name):
            await message.answer(f"✅ Таблица билетов установлена на лист '{sheet_name}'")


@router.message(Command("exam_logs"), HasRole(Role.OWNER))
async def cmd_exam_logs(message: Message, sheets: SheetsClient, storage: Storage):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        exams = ExamRepository(sheets, storage)
        logs_name = await exams.get_log_sheet_name()
        await message.answer(
            dedent(
                f"""\
                📝 Текущий лист сдачи: {logs_name or "не настроен"}

                📝 Использование: /exam_logs <url>
                """
            ).strip()
        )
        return

    exams = ExamRepository(sheets, storage)
    match await exams.set_exam_log(args[1].strip()):
        case Fail(error):
            await message.answer(EXAM_ERROR_MESSAGES[error])
        case Ok(sheet_name):
            await message.answer(f"✅ Таблица сдачи установлена на лист '{sheet_name}'")


@router.message(Command("exam"), HasRole(Role.TEAM))
async def cmd_exam_status(message: Message, sheets: SheetsClient, storage: Storage):
    exams = ExamRepository(sheets, storage)
    status = await exams.get_exam_status()
    tasks = status.tasks
    logs = status.logs

    if tasks is None or logs is None:
        await message.answer("❌ Ошибка: не удалось получить статус.")
        return

    if tasks.spreadsheet_id and tasks.sheet_name:
        tasks_gid = await sheets.resolve_sheet_gid(tasks.spreadsheet_id, tasks.sheet_name)
        tasks_link = f"https://docs.google.com/spreadsheets/d/{tasks.spreadsheet_id}/edit#gid={tasks_gid}"
        tasks_line = f"- Билеты: [{tasks.sheet_name}]({tasks_link}) ({tasks.count} записей) - {tasks.status}"
    else:
        tasks_line = "- Билеты: не настроены"

    if logs.spreadsheet_id and logs.sheet_name:
        logs_gid = await sheets.resolve_sheet_gid(logs.spreadsheet_id, logs.sheet_name)
        logs_link = f"https://docs.google.com/spreadsheets/d/{logs.spreadsheet_id}/edit#gid={logs_gid}"
        logs_line = f"- Сдача: [{logs.sheet_name}]({logs_link}) ({logs.count} записей) - {logs.status}"
    else:
        logs_line = "- Сдача: не настроена"

    await message.answer(
        dedent(
            f"""\
            📊 Конфигурация экзамена:
            {tasks_line}
            {logs_line}
            """
        ).strip(),
        parse_mode="Markdown",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@router.message(Command("exam_end"), HasRole(Role.OWNER))
async def cmd_exam_end(message: Message, sheets: SheetsClient, storage: Storage):
    exams = ExamRepository(sheets, storage)
    exams.clear_exam_config()
    await message.answer("✅ Экзамен завершен. Конфигурация таблиц сброшена.")
