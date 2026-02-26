from enum import Enum

from aiogram.filters import BaseFilter
from aiogram.types import Message

from itmogus.core.config import config
from itmogus.modules.users.repository import UserRepository
from itmogus.sheets.sheet import SheetsClient


class Role(Enum):
    OWNER = "owner"
    TEAM = "team"
    GUEST = "guest"


async def get_role(user_id: int, users: UserRepository) -> Role:
    if is_owner(user_id):
        return Role.OWNER
    if await is_team(user_id, users):
        return Role.TEAM
    return Role.GUEST


def is_owner(user_id: int) -> bool:
    return user_id in config.owner_ids


async def is_team(user_id: int, users: UserRepository) -> bool:
    return user_id in await users.get_team_member_ids()


class HasRole(BaseFilter):
    def __init__(self, min_role: Role):
        self.min_role = min_role

    async def __call__(self, message: Message, sheets: SheetsClient) -> bool:
        user = message.from_user
        if user is None:
            return False

        users = UserRepository(sheets)
        user_id = user.id
        allowed = False

        if self.min_role == Role.OWNER:
            allowed = is_owner(user_id)
        elif self.min_role == Role.TEAM:
            allowed = is_owner(user_id) or await is_team(user_id, users)

        if not allowed:
            await message.answer("У вас нет доступа к этой команде.")
        return allowed
