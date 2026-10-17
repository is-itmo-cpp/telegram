from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from itmogus.labs import get_student_repo_name, resolve_lab_name
from itmogus.sheets import cell, parse_int


TIME_FORMAT = "%d.%m.%Y %H:%M:%S"


@dataclass
class ReviewRequest:
    _headers: ClassVar[list[list[str]]] = [
        ["Время", "Лаба", "Ссылка на PR", "Проверил", "Который раз", "Репо"],
    ]

    submitted_at: datetime
    lab: str
    checker: str
    attempt: int
    repo: str

    @classmethod
    def from_row(cls, row: list[str]) -> "ReviewRequest | None":
        lab = resolve_lab_name(cell(row, 1))
        attempt = parse_int(cell(row, 4))
        repo = cell(row, 5)
        if lab is None or attempt is None or not repo:
            return None
        try:
            submitted_at = datetime.strptime(cell(row, 0), TIME_FORMAT)
        except ValueError:
            return None
        return cls(
            submitted_at=submitted_at,
            lab=lab,
            checker=cell(row, 3),
            attempt=attempt,
            repo=repo,
        )

    @property
    def is_checked(self) -> bool:
        return bool(self.checker)

    @property
    def sort_key(self) -> tuple[int, datetime]:
        return self.attempt, self.submitted_at


@dataclass
class QueuePosition:
    lab: str
    position: int


def get_queue_positions(requests: list[ReviewRequest], github_username: str) -> list[QueuePosition]:
    queues: dict[str, list[ReviewRequest]] = {}
    for request in requests:
        if not request.is_checked:
            queues.setdefault(request.lab, []).append(request)

    positions: list[QueuePosition] = []
    for lab, queue in queues.items():
        queue.sort(key=lambda request: request.sort_key)
        repo = get_student_repo_name(lab, github_username).casefold()
        for index, request in enumerate(queue):
            if request.repo.casefold() == repo:
                positions.append(QueuePosition(lab=lab, position=index + 1))
                break

    return positions
