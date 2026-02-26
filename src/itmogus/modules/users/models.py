from dataclasses import dataclass
from typing import Any, ClassVar

from itmogus.sheets import cell, parse_int


@dataclass
class Student:
    _headers: ClassVar[list[list[str]]] = [
        ["ISU", "Group", "Name", "GitHub"],
    ]

    isu: int
    group: str
    name: str
    github: str = ""

    @classmethod
    def from_row(cls, row: list[str]) -> "Student | None":
        isu = parse_int(cell(row, 0))
        if isu is None:
            return None
        return cls(
            isu=isu,
            group=cell(row, 1),
            name=cell(row, 2),
            github=cell(row, 3),
        )

    def to_row(self) -> list[Any]:
        return [self.isu, self.group, self.name, self.github]


@dataclass
class BotUser:
    _headers: ClassVar[list[list[str]]] = [
        ["ISU", "Telegram ID"],
    ]

    isu: int
    telegram_id: int

    @classmethod
    def from_row(cls, row: list[str]) -> "BotUser | None":
        isu = parse_int(cell(row, 0))
        telegram_id = parse_int(cell(row, 1))
        if isu is None or telegram_id is None:
            return None
        return cls(isu=isu, telegram_id=telegram_id)

    def to_row(self) -> list[Any]:
        return [self.isu, self.telegram_id]


@dataclass
class TeamMember:
    _headers: ClassVar[list[list[str]]] = [
        ["Telegram ID", "Name"],
    ]

    telegram_id: int
    name: str

    @classmethod
    def from_row(cls, row: list[str]) -> "TeamMember | None":
        telegram_id = parse_int(cell(row, 0))
        if telegram_id is None:
            return None
        return cls(telegram_id=telegram_id, name=cell(row, 1))

    def to_row(self) -> list[Any]:
        return [self.telegram_id, self.name]
