from dataclasses import dataclass
from typing import Any, ClassVar

from itmogus.sheets import cell


@dataclass
class Task:
    _headers: ClassVar[list[list[str]]] = [
        ["№", "Название", "Баллы", "Текст задания", "Комментарии для принимающих"],
    ]

    id: str
    name: str
    points: str
    text: str

    @classmethod
    def from_row(cls, row: list[str]) -> "Task | None":
        task_id = cell(row, 0)
        if not task_id:
            return None
        return cls(
            id=task_id,
            name=cell(row, 1),
            points=cell(row, 2),
            text=cell(row, 3),
        )

    def to_row(self) -> list[Any]:
        return [self.id, self.name, self.points, self.text, ""]


@dataclass
class ExamLog:
    _headers: ClassVar[list[list[str]]] = [
        ["Студент", "", "", "Время", "", "Задание", "", "", "Проверяющий", "Комментарий"],
        ["ИСУ", "Группа", "ФИО", "Начало", "Прошло", "№", "Max", "Итог", "", ""],
    ]

    isu: int
    group: str
    name: str
    started_at: str
    elapsed: str
    task_id: str
    points_max: str
    points_total: str
    checker: str
    comment: str

    def to_row(self) -> list[Any]:
        return [
            self.isu,
            self.group,
            self.name,
            self.started_at,
            self.elapsed,
            self.task_id,
            self.points_max,
            self.points_total,
            self.checker,
            self.comment,
        ]


@dataclass
class ExamSheetStatus:
    spreadsheet_id: str = ""
    sheet_name: str = ""
    count: int = 0
    status: str = "⚠️ не настроен"


@dataclass
class ExamStatus:
    configured: bool
    tasks: ExamSheetStatus | None = None
    logs: ExamSheetStatus | None = None
