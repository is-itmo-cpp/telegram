from itmogus.core.config import config
from itmogus.modules.users.errors import (
    IsuAlreadyBoundError,
    NoSuchIsuError,
    TelegramAlreadyBoundError,
)
from itmogus.modules.users.models import BotUser, Student, TeamMember
from itmogus.sheets import Sheet, SheetsClient


STUDENTS_SHEET = "Students"
BOT_USERS_SHEET = "Users"
TEAM_SHEET = "Team"


class UserRepository:
    def __init__(self, client: SheetsClient, table_id: str = ""):
        self._client = client
        self._table_id = table_id or config.users_table_id

    def _students_sheet(self) -> Sheet:
        return self._client.get_sheet_by_name(self._table_id, STUDENTS_SHEET)

    def _bot_users_sheet(self) -> Sheet:
        return self._client.get_sheet_by_name(self._table_id, BOT_USERS_SHEET)

    def _team_sheet(self) -> Sheet:
        return self._client.get_sheet_by_name(self._table_id, TEAM_SHEET)

    async def get_all_students(self) -> dict[int, Student]:
        students = await self._students_sheet().read_models(Student)
        return {student.isu: student for student in students}

    async def get_student_by_isu(self, isu: int) -> Student | None:
        students = await self.get_all_students()
        return students.get(isu)

    async def get_all_bot_users(self) -> dict[int, BotUser]:
        users = await self._bot_users_sheet().read_models(BotUser)
        return {user.telegram_id: user for user in users}

    async def get_all_bot_users_by_isu(self) -> dict[int, BotUser]:
        users = await self._bot_users_sheet().read_models(BotUser)
        return {user.isu: user for user in users}

    async def get_user_by_telegram_id(self, tg_id: int) -> BotUser | None:
        users = await self.get_all_bot_users()
        return users.get(tg_id)

    async def get_user_by_isu(self, isu: int) -> BotUser | None:
        users = await self.get_all_bot_users_by_isu()
        return users.get(isu)

    async def register_user(self, tg_id: int, isu: int) -> Student:
        users = await self.get_all_bot_users()
        user_by_tg = users.get(tg_id)
        if user_by_tg is not None:
            raise TelegramAlreadyBoundError()

        isu_matches = [user for user in users.values() if user.isu == isu]
        if any(user.telegram_id != tg_id for user in isu_matches):
            raise IsuAlreadyBoundError()

        if (student := await self.get_student_by_isu(isu)) is None:
            raise NoSuchIsuError()

        await self._bot_users_sheet().append_model(BotUser(isu=isu, telegram_id=tg_id))

        return student

    async def get_all_team_members(self) -> list[TeamMember]:
        return await self._team_sheet().read_models(TeamMember)

    async def get_team_member_ids(self) -> set[int]:
        members = await self.get_all_team_members()
        return {m.telegram_id for m in members}
