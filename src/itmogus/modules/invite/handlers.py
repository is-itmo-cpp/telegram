import logging
from dataclasses import dataclass
from textwrap import dedent

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from itmogus.core.actions import CANCEL, CONFIRM, Action, PendingActions, action_button
from itmogus.labs import resolve_lab_name
from itmogus.modules.invite.errors import InviteError
from itmogus.modules.invite.github import (
    ensure_invitation,
    EnsureStatus,
    RolloutPhase,
    RolloutProgress,
    run_rollout,
)
from itmogus.modules.users.auth import HasRole, Role
from itmogus.modules.users.repository import UserRepository
from itmogus.progress import render_progress_bar, run_with_progress
from itmogus.result import Fail, Ok
from itmogus.sheets.sheet import SheetsClient


logger = logging.getLogger(__name__)


router = Router()
current_rollout: RolloutProgress | None = None

ROLLOUT_CANCEL_TTL = 6 * 60 * 60


@dataclass(frozen=True)
class RolloutPayload:
    lab_name: str


@dataclass(frozen=True)
class CancelRolloutPayload:
    lab_name: str


def _render_rollout_progress(lab_name: str, progress: RolloutProgress) -> str:
    match progress.phase:
        case RolloutPhase.CHECKING_TEMPLATE:
            return f"🔍 Проверяю шаблон для `{lab_name}`..."
        case RolloutPhase.LISTING_FORKS:
            return dedent(
                f"""\
                🔍 Ищу существующие форки...

                🧪 Лабораторная: `{lab_name}`
                🍴 Найдено: {progress.forks_found}
                """
            ).strip()
        case RolloutPhase.CREATING_FORKS:
            bar = render_progress_bar(progress.completed, progress.total)
            return dedent(
                f"""\
                🍴 Создаю форки...

                🧪 Лабораторная: `{lab_name}`
                {bar} {progress.completed}/{progress.total}
                ✅ Уже существовали: {progress.forks_existing}
                🆕 Создано: {progress.forks_created}
                ❌ Ошибки: {progress.fork_errors}
                """
            ).strip()
        case RolloutPhase.SENDING_INVITATIONS:
            bar = render_progress_bar(progress.completed, progress.total)
            return dedent(
                f"""\
                📨 Отправляю приглашения...

                🧪 Лабораторная: `{lab_name}`
                {bar} {progress.completed}/{progress.total}
                📨 Отправлено: {progress.invitations_sent}
                ✅ Доступ уже был: {progress.already_accessible}
                ❌ Ошибки: {progress.invitation_errors}
                ⚙️ Ошибки включения Actions: {progress.actions_errors}
                """
            ).strip()


def _render_rollout_result(lab_name: str, progress: RolloutProgress, header: str = "✅ Rollout завершён") -> str:
    return dedent(
        f"""\
        {header}

        🧪 Лабораторная: `{lab_name}`
        👥 Студентов: {progress.students}
        🐙 GitHub-аккаунтов: {progress.github_accounts}
        ⚠️ Без GitHub: {progress.missing_github}
        ⚠️ Повторяющиеся GitHub: {progress.duplicate_github}

        🍴 Уже существовали: {progress.forks_existing}
        🆕 Форков создано: {progress.forks_created}
        ❌ Ошибки форков: {progress.fork_errors}

        📨 Приглашений отправлено: {progress.invitations_sent}
        ✅ Доступ уже был: {progress.already_accessible}
        ❌ Ошибки приглашений: {progress.invitation_errors}
        ⚙️ Ошибки включения Actions: {progress.actions_errors}
        """
    ).strip()


@router.message(Command("rollout"), HasRole(Role.TEAM), F.chat.type == "private")
async def cmd_rollout(message: Message, actions: PendingActions):
    if message.from_user is None:
        return

    if current_rollout is not None:
        await message.answer("⏳ Rollout уже выполняется. Дождитесь его завершения.")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("📝 Использование: /rollout <lab>\n\nПример: /rollout 6")
        return

    lab_name = resolve_lab_name(args[1])
    if lab_name is None:
        await message.answer(
            "❌ Укажите положительное число или название (например: /rollout 6, /rollout livecoding2)."
        )
        return

    token = actions.create(owner_id=message.from_user.id, payload=RolloutPayload(lab_name=lab_name))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                action_button("✅ Запустить", token, CONFIRM),
                action_button("❌ Отмена", token, CANCEL),
            ]
        ]
    )
    await message.answer(
        dedent(
            f"""\
            ⚠️ Запустить rollout для `{lab_name}`?
            """
        ).strip(),
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@router.callback_query(Action(RolloutPayload), HasRole(Role.TEAM))
async def callback_rollout(
    callback: CallbackQuery,
    payload: RolloutPayload,
    choice: str,
    sheets: SheetsClient,
    actions: PendingActions,
):
    global current_rollout

    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    if choice != CONFIRM:
        await callback.message.edit_text("❌ Rollout отменён.")
        await callback.answer()
        return

    lab_name = payload.lab_name

    if current_rollout is not None:
        await callback.answer("Rollout уже выполняется. Дождитесь его завершения.", show_alert=True)
        return

    cancel_token = actions.create(
        owner_id=callback.from_user.id,
        payload=CancelRolloutPayload(lab_name=lab_name),
        ttl=ROLLOUT_CANCEL_TTL,
    )
    cancel_keyboard = InlineKeyboardMarkup(inline_keyboard=[[action_button("⛔ Остановить", cancel_token)]])

    progress = RolloutProgress()
    current_rollout = progress
    try:
        await callback.answer()

        users = UserRepository(sheets)
        students = list((await users.get_all_students()).values())
        github_usernames_by_key: dict[str, str] = {}
        github_entries = 0
        for student in students:
            username = student.github.strip()
            if not username:
                continue
            github_entries += 1
            github_usernames_by_key.setdefault(username.casefold(), username)

        github_usernames = list(github_usernames_by_key.values())
        progress.students = len(students)
        progress.github_accounts = len(github_usernames)
        progress.missing_github = len(students) - github_entries
        progress.duplicate_github = github_entries - len(github_usernames)
        await callback.message.edit_text(
            _render_rollout_progress(lab_name, progress),
            parse_mode="Markdown",
            reply_markup=cancel_keyboard,
        )

        try:
            error = await run_with_progress(
                callback.message,
                run_rollout(lab_name, github_usernames, progress),
                lambda: _render_rollout_progress(lab_name, progress),
                parse_mode="Markdown",
                reply_markup=cancel_keyboard,
            )
        except Exception:
            logger.exception("Rollout failed for lab '%s'", lab_name)
            await callback.message.edit_text("❌ Rollout завершился с ошибкой. Попробуйте позже.")
            return

        match error:
            case InviteError.TEMPLATE_NOT_FOUND:
                await callback.message.edit_text("❌ Шаблон репозитория не найден.")
            case InviteError.TEMPLATE_NOT_PRIVATE:
                await callback.message.edit_text("❌ Шаблон репозитория должен быть приватным.")
            case InviteError.CANCELLED:
                await callback.message.edit_text(
                    _render_rollout_result(lab_name, progress, header="⛔ Rollout остановлен"),
                    parse_mode="Markdown",
                )
            case None:
                await callback.message.edit_text(
                    _render_rollout_result(lab_name, progress),
                    parse_mode="Markdown",
                )
    finally:
        current_rollout = None
        actions.consume(cancel_token)


@router.callback_query(Action(CancelRolloutPayload), HasRole(Role.TEAM))
async def callback_cancel_rollout(callback: CallbackQuery, payload: CancelRolloutPayload, choice: str):
    if current_rollout is None:
        await callback.answer("Rollout уже завершён.")
        return

    current_rollout.cancel_requested = True
    await callback.answer("⛔ Останавливаю rollout...")


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
        case Fail(InviteError.REPO_NOT_FOUND):
            await message.answer("❌ Репозиторий для этой лабораторной ещё не создан. Обратитесь к преподавателю.")
        case Fail(InviteError.GITHUB_ERROR):
            await message.answer("❌ Ошибка GitHub. Попробуйте позже.")
        case Fail(error):
            await message.answer(f"❌ Произошла ошибка: {error}.")
