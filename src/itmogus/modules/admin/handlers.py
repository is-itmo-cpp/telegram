import json
from pathlib import Path
from textwrap import dedent

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions, Message

from itmogus.core.config import config
from itmogus.modules.users.auth import HasRole, Role
from itmogus.sheets.sheet import SheetsClient


router = Router()

LOGS_DIR = Path("logs")


# Just reads the entire 10MB file. That'll do ¯\(ツ)/¯
def read_logs(limit: int, criteria: tuple[str, str | int] | None = None) -> list[dict]:
    log_file = LOGS_DIR / "itmogus.log"
    if not log_file.exists():
        return []

    logs = []
    with open(log_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                log_entry = json.loads(line)
                if criteria:
                    key, value = criteria
                    log_value = log_entry.get(key)
                    if key == "event_id":
                        if not isinstance(log_value, str) or not log_value.startswith(str(value)):
                            continue
                    elif log_value != value:
                        continue
                logs.append(log_entry)
            except json.JSONDecodeError:
                continue

    return logs[-limit:]


def format_log_entry(log: dict) -> str:
    timestamp = log.get("timestamp", "?")
    level = log.get("level", "?")
    message = log.get("message", "?")
    event_id = log.get("event_id", "")
    user_id = log.get("user_id", "")

    parts = [f"[{timestamp}]", f"[{level}]"]
    if event_id:
        parts.append(f"[{event_id[:8]}]")
    if user_id:
        parts.append(f"[user:{user_id}]")
    parts.append(message)

    return " ".join(parts)


@router.message(Command("logs"), HasRole(Role.OWNER), F.chat.type == "private")
async def cmd_log(message: Message):
    args = (message.text or "").split()[1:]

    if not args or args[0] == "help":
        await message.answer(
            dedent(
                """\
                📋 **Log viewer**

                Usage: `/logs [criteria] [count]`

                **Examples:**
                `/logs` - Last 20 logs
                `/logs 50` - Last 50 logs
                `/logs error` - Last 20 errors
                `/logs warning 30` - Last 30 warnings
                `/logs user:123456` - Last 20 logs from user 123456
                `/logs event:abc123` - Last 20 logs with event ID abc123

                **Levels:** error, warning, info, debug
                **Max count:** 100
                """
            ).strip(),
            parse_mode="Markdown",
        )
        return

    criteria = None
    count = 20

    for arg in args:
        if arg.isdigit():
            count = min(int(arg), 100)
        elif arg in ("error", "warning", "info", "debug"):
            criteria = ("level", arg.upper())
        elif arg.startswith("user:"):
            try:
                criteria = ("user_id", int(arg.split(":")[1]))
            except (ValueError, IndexError):
                await message.answer(f"Invalid user ID: {arg}")
                return
        elif arg.startswith("event:"):
            criteria = ("event_id", arg.split(":", 1)[1])

    logs = read_logs(count, criteria)

    if not logs:
        await message.answer("No logs found.")
        return

    formatted = [format_log_entry(log) for log in logs]
    text = "\n".join(formatted)

    await message.answer(f"```\n{text}\n```", parse_mode="Markdown")


@router.message(Command("reload"), HasRole(Role.OWNER))
async def cmd_reload(message: Message, sheets: SheetsClient):
    sheets.invalidate_all_sheets()
    await message.answer("✅ Кэш сброшен.")


@router.message(Command("status"), HasRole(Role.OWNER), F.chat.type == "private")
async def cmd_status(message: Message, sheets: SheetsClient):
    async def _link(sheet_name: str) -> str:
        gid = await sheets.resolve_sheet_gid(config.users_table_id, sheet_name)
        url = f"https://docs.google.com/spreadsheets/d/{config.users_table_id}/edit#gid={gid}"
        return f"[{sheet_name}]({url})"

    students_link = await _link("Students")
    users_link = await _link("Users")
    permissions_link = await _link("Team")

    await message.answer(
        dedent(
            f"""\
            ⚙️ Текущая конфигурация:

            - Лист прав: {permissions_link}
            - Лист регистраций: {users_link}
            - Лист студентов: {students_link}
            - Github org: `{config.github_org}`
            """
        ).strip(),
        parse_mode="Markdown",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
