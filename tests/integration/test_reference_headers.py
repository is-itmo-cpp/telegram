import os

import pytest

from itmogus.sheets import parse_sheets_url
from itmogus.modules.exam.models import ExamLog, Task
from itmogus.modules.users.models import BotUser, Student, TeamMember
from itmogus.modules.users.repository import (
    BOT_USERS_SHEET,
    TEAM_SHEET,
    STUDENTS_SHEET,
)


def _reference_cases() -> list[tuple[str, str, list[list[str]]]]:
    return [
        ("exam-log", os.environ["TEST_EXAM_LOG_SHEET_URL"], ExamLog._headers),
        (
            "exam-tasks",
            os.environ["TEST_EXAM_TASKS_SHEET_URL"],
            Task._headers,
        ),
    ]


def _extract_spreadsheet_id(url: str) -> str | None:
    parsed = parse_sheets_url(url)
    if parsed is not None:
        return parsed[0]

    parsed_with_default_gid = parse_sheets_url(f"{url}#gid=0")
    if parsed_with_default_gid is not None:
        return parsed_with_default_gid[0]

    return None


def _users_cases() -> list[tuple[str, str, str, list[list[str]]]]:
    spreadsheet_url = os.environ["TEST_USERS_SHEETS_URL"]
    spreadsheet_id = _extract_spreadsheet_id(spreadsheet_url)
    assert spreadsheet_id is not None, f"invalid users sheets URL: {spreadsheet_url}"
    return [
        ("team", spreadsheet_id, TEAM_SHEET, TeamMember._headers),
        ("students", spreadsheet_id, STUDENTS_SHEET, Student._headers),
        ("users", spreadsheet_id, BOT_USERS_SHEET, BotUser._headers),
    ]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "sheet_url", "expected_headers"),
    _reference_cases(),
    ids=[case[0] for case in _reference_cases()],
)
async def test_reference_sheet_headers_match(
    sheets_client, case_name: str, sheet_url: str, expected_headers: list[list[str]]
) -> None:
    parsed = parse_sheets_url(sheet_url)
    assert parsed is not None, f"invalid URL for {case_name}: {sheet_url}"

    spreadsheet_id, gid = parsed
    sheet_name = await sheets_client.resolve_sheet_name(spreadsheet_id, gid)
    sheet = sheets_client.get_sheet_by_name(spreadsheet_id, sheet_name)
    await sheet.assert_headers(expected_headers)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_name", "spreadsheet_id", "sheet_name", "expected_headers"),
    _users_cases(),
    ids=[case[0] for case in _users_cases()],
)
async def test_reference_users_sheet_headers_match(
    sheets_client,
    case_name: str,
    spreadsheet_id: str,
    sheet_name: str,
    expected_headers: list[list[str]],
) -> None:
    sheet = sheets_client.get_sheet_by_name(spreadsheet_id, sheet_name)
    await sheet.assert_headers(expected_headers)
