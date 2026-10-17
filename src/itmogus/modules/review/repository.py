import logging

from itmogus.core.storage import Storage
from itmogus.modules.review.errors import ReviewConfigError
from itmogus.modules.review.models import ReviewRequest
from itmogus.modules.review.state import ReviewState
from itmogus.result import Fail, Ok, Result
from itmogus.sheets import SheetNotFoundError, SheetsSchemaError, SheetRef, parse_sheets_url
from itmogus.sheets.sheet import Sheet, SheetsClient


logger = logging.getLogger(__name__)


class ReviewRepository:
    def __init__(self, client: SheetsClient, state: Storage):
        self._client = client
        self._state = state

    def _review_state(self) -> ReviewState:
        return self._state.get("review", ReviewState)

    def _requests_sheet(self) -> Sheet | None:
        ref = self._review_state().requests
        if not ref.spreadsheet_id or not ref.sheet_name:
            return None
        return self._client.get_sheet_by_name(ref.spreadsheet_id, ref.sheet_name)

    def get_requests_sheet_name(self) -> str:
        return self._review_state().requests.sheet_name

    def is_configured(self) -> bool:
        return self._requests_sheet() is not None

    async def get_all_requests(self) -> list[ReviewRequest]:
        sheet = self._requests_sheet()
        if sheet is None:
            return []
        return await sheet.read_models(ReviewRequest)

    async def set_requests_sheet(self, url: str) -> Result[str, ReviewConfigError]:
        parsed = parse_sheets_url(url)
        if not parsed:
            return Fail(ReviewConfigError.INVALID_URL)

        spreadsheet_id, gid = parsed

        try:
            sheet = await self._client.get_sheet_by_gid(spreadsheet_id, gid)
            await sheet.assert_model_headers(ReviewRequest)
        except SheetsSchemaError:
            return Fail(ReviewConfigError.SCHEMA_MISMATCH)
        except SheetNotFoundError:
            return Fail(ReviewConfigError.SHEET_NOT_FOUND)

        state = self._review_state()
        state.requests = SheetRef(spreadsheet_id=spreadsheet_id, sheet_name=sheet.name)
        self._state.save("review")

        logger.info("Review queue sheet set to '%s'", sheet.name)
        return Ok(sheet.name)
