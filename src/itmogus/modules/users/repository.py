import logging
from enum import Enum

from itmogus.core.config import config
from itmogus.modules.users.models import BotUser, Student, TeamMember
from itmogus.result import Fail, Ok, Result
from itmogus.sheets import Sheet, SheetsClient


logger = logging.getLogger(__name__)

STUDENTS_SHEET = "Students"
BOT_USERS_SHEET = "Users"
TEAM_SHEET = "Team"


class RegisterError(Enum):
    TELEGRAM_ALREADY_BOUND = "telegram_already_bound"
    ISU_ALREADY_BOUND = "isu_already_bound"
    NO_SUCH_ISU = "no_such_isu"


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

    async def register_user(self, tg_id: int, isu: int) -> Result[Student, RegisterError]:
        users = await self.get_all_bot_users()
        user_by_tg = users.get(tg_id)
        if user_by_tg is not None:
            return Fail(RegisterError.TELEGRAM_ALREADY_BOUND)

        isu_matches = [user for user in users.values() if user.isu == isu]
        if any(user.telegram_id != tg_id for user in isu_matches):
            return Fail(RegisterError.ISU_ALREADY_BOUND)

        student = await self.get_student_by_isu(isu)
        if student is None:
            return Fail(RegisterError.NO_SUCH_ISU)

        await self._bot_users_sheet().append_model(BotUser(isu=isu, telegram_id=tg_id))

        logger.info("User %d registered as ISU %d (%s)", tg_id, isu, student.name)

        return Ok(student)

    async def get_all_team_members(self) -> list[TeamMember]:
        return await self._team_sheet().read_models(TeamMember)

    async def get_team_member_ids(self) -> set[int]:
        members = await self.get_all_team_members()
        return {m.telegram_id for m in members}
