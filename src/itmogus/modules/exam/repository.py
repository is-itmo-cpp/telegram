import logging
from datetime import datetime

from itmogus.core.storage import Storage
from itmogus.modules.exam.errors import ExamConfigError
from itmogus.modules.exam.models import ExamLog, ExamSheetStatus, ExamStatus, Task
from itmogus.modules.exam.state import ExamState
from itmogus.sheets import SheetRef, SheetsSchemaError, parse_sheets_url
from itmogus.sheets.sheet import HeaderModel, Sheet, SheetsClient


logger = logging.getLogger(__name__)


class ExamRepository:
    def __init__(self, client: SheetsClient, state: Storage):
        self._client = client
        self._state = state

    def _exam_state(self) -> ExamState:
        return self._state.get("exam", ExamState)

    async def _get_sheet(self, ref: SheetRef) -> Sheet | None:
        if not ref.spreadsheet_id or not ref.sheet_name:
            return None
        return self._client.get_sheet_by_name(ref.spreadsheet_id, ref.sheet_name)

    async def _get_sheet_name(self, ref: SheetRef) -> str:
        sheet = await self._get_sheet(ref)
        if sheet is None:
            return ""
        return sheet.name

    async def get_tasks_sheet_name(self) -> str:
        return await self._get_sheet_name(self._exam_state().tasks)

    async def get_log_sheet_name(self) -> str:
        return await self._get_sheet_name(self._exam_state().log)

    async def get_all_tasks(self) -> dict[str, Task]:
        ref = self._exam_state().tasks
        sheet = await self._get_sheet(ref)
        if sheet is None:
            return {}

        tasks = await sheet.read_models(Task)
        return {task.id: task for task in tasks if task.id}

    async def log_exam(self, isu: int, name: str, task_comment: str | None, points: str) -> None:
        sheet = await self._get_sheet(self._exam_state().log)
        if sheet is None:
            return

        await sheet.assert_model_headers(ExamLog)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await sheet.append_model(
            ExamLog(
                isu=isu,
                group="",
                name=name,
                started_at=timestamp,
                elapsed="",
                points_max=points,
                points_total="",
                checker="",
                comment=task_comment or "",
            )
        )

        logger.info("Task %s (%s points) assigned to ISU %d", task_comment, points, isu)

    async def set_exam_tasks(self, url: str) -> str:
        parsed = parse_sheets_url(url)
        if not parsed:
            raise ExamConfigError("Не удалось распознать ссылку.")

        spreadsheet_id, gid = parsed

        try:
            sheet = await self._client.get_sheet_by_gid(spreadsheet_id, gid)
            await sheet.assert_model_headers(Task)
        except SheetsSchemaError:
            raise
        except Exception as e:
            raise ExamConfigError(f"Не удалось найти лист с gid={gid}") from e

        state = self._exam_state()
        state.tasks = SheetRef(spreadsheet_id=spreadsheet_id, sheet_name=sheet.name)
        self._state.save("exam")
        self._client.invalidate_all_sheets()

        logger.info("Exam tasks sheet set to '%s'", sheet.name)
        return f"Таблица билетов установлена на лист '{sheet.name}'"

    async def set_exam_log(self, url: str) -> str:
        parsed = parse_sheets_url(url)
        if not parsed:
            raise ExamConfigError("Не удалось распознать ссылку.")

        spreadsheet_id, gid = parsed

        try:
            sheet = await self._client.get_sheet_by_gid(spreadsheet_id, gid)
            await sheet.assert_model_headers(ExamLog)
        except SheetsSchemaError:
            raise
        except Exception as e:
            raise ExamConfigError(f"Не удалось найти лист с gid={gid}") from e

        state = self._exam_state()
        state.log = SheetRef(spreadsheet_id=spreadsheet_id, sheet_name=sheet.name)
        self._state.save("exam")
        self._client.invalidate_all_sheets()

        logger.info("Exam log sheet set to '%s'", sheet.name)
        return f"Таблица сдачи установлена на лист '{sheet.name}'"

    async def _sheet_status(self, ref: SheetRef, model_cls: type[HeaderModel]) -> ExamSheetStatus:
        sheet = await self._get_sheet(ref)
        if sheet is None:
            return ExamSheetStatus(status="⚠️ не настроен")

        if not sheet.name:
            return ExamSheetStatus(spreadsheet_id=ref.spreadsheet_id, sheet_name="", status="⚠️ не найден")

        await sheet.assert_model_headers(model_cls)
        rows = await sheet.get_rows()
        count = max(0, len(rows) - 1)
        return ExamSheetStatus(
            spreadsheet_id=ref.spreadsheet_id,
            sheet_name=sheet.name,
            count=count,
            status="✅ валиден",
        )

    async def get_exam_status(self) -> ExamStatus:
        state = self._exam_state()
        tasks = await self._sheet_status(state.tasks, Task)
        logs = await self._sheet_status(state.log, ExamLog)
        configured = bool(state.tasks.spreadsheet_id or state.log.spreadsheet_id)
        return ExamStatus(configured=configured, tasks=tasks, logs=logs)

    def clear_exam_config(self) -> None:
        state = self._exam_state()
        state.tasks = SheetRef()
        state.log = SheetRef()
        self._state.save("exam")
        self._client.invalidate_all_sheets()

        logger.info("Exam config cleared")
