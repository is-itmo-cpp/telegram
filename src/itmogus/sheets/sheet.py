from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ClassVar, Protocol, Self, TypeVar

from aiogoogle.auth.creds import ServiceAccountCreds
from aiogoogle.client import Aiogoogle
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from itmogus.sheets.cache import TTLCache
from itmogus.sheets.errors import (
    SheetNotFoundError,
    SheetsAPIError,
    SheetsConnectionError,
    SheetsRateLimitError,
    SheetsSchemaError,
    map_http_error,
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_RETRIES = 3
SHEETS_CACHE_TTL_SECONDS = 600.0
SHEETS_CACHE_MAXSIZE = 100


class HeaderModel(Protocol):
    _headers: ClassVar[list[list[str]]]


class DeserializableRowModel(HeaderModel, Protocol):
    @classmethod
    def from_row(cls, row: list[str]) -> Self | None: ...


class SerializableRowModel(HeaderModel, Protocol):
    def to_row(self) -> list[Any]: ...


DeserializableModelT = TypeVar("DeserializableModelT", bound=DeserializableRowModel)


def _normalize_cell(value: str) -> str:
    return value.strip().lower()


def _quote_sheet_name(sheet_name: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'"


@dataclass
class Sheet:
    _client: SheetsClient
    spreadsheet_id: str
    name: str
    _rows_cache: TTLCache = field(default_factory=lambda: TTLCache(SHEETS_CACHE_TTL_SECONDS))

    async def get_rows(self) -> list[list[str]]:
        rows = await self._rows_cache.get_or_load(self._load_rows)
        return [list(row) for row in rows]

    async def append_row(self, values: list[Any]) -> None:
        await self._client.append_row(self.spreadsheet_id, self.name, values)
        self.invalidate_cache()

    async def append_model(self, item: SerializableRowModel) -> None:
        await self.assert_headers(item._headers)
        await self.append_row(item.to_row())

    async def assert_headers(self, expected_rows: list[list[str]]) -> None:
        if not expected_rows:
            raise ValueError("Expected at least one header row")

        header_row_count = len(expected_rows)

        actual_rows = await self._client.get_header_rows(self.spreadsheet_id, self.name, header_row_count)
        _assert_headers_match(expected_rows, actual_rows, self.name)

    async def assert_model_headers(self, model_cls: type[HeaderModel]) -> None:
        await self.assert_headers(_model_headers(model_cls))

    async def read_models(self, model_cls: type[DeserializableModelT]) -> list[DeserializableModelT]:
        expected_headers = _model_headers(model_cls)
        rows = await self.get_rows()
        _assert_headers_match(expected_headers, rows, self.name)

        data_start_row = len(expected_headers)
        if len(rows) <= data_start_row:
            return []

        records: list[DeserializableModelT] = []
        for row_number, row in enumerate(rows[data_start_row:], start=data_start_row + 1):
            try:
                item = model_cls.from_row(row)
            except Exception as error:  # noqa: BLE001
                raise SheetsSchemaError(f"Invalid row {row_number} in '{self.name}': {error}") from error
            if item is not None:
                records.append(item)

        return records

    def invalidate_cache(self) -> None:
        self._rows_cache.invalidate()

    async def _load_rows(self) -> list[list[str]]:
        return await self._client.get_rows(self.spreadsheet_id, self.name)


@dataclass
class SheetsClient:
    _aiogoogle: Aiogoogle
    _service: Any
    _sheets: dict[tuple[str, str], Sheet] = field(default_factory=dict)

    @classmethod
    async def create(cls, credentials_path: str) -> "SheetsClient":
        creds_path = Path(credentials_path)
        if not creds_path.exists():
            raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

        with open(creds_path) as file:
            creds_data = json.load(file)

        creds = ServiceAccountCreds(scopes=SCOPES, **creds_data)
        aiogoogle = Aiogoogle(service_account_creds=creds)
        await aiogoogle.__aenter__()
        service = await aiogoogle.discover("sheets", "v4")
        logger.info("Sheets service initialized")
        return cls(_aiogoogle=aiogoogle, _service=service)

    async def close(self) -> None:
        await self._aiogoogle.__aexit__(None, None, None)
        self._sheets.clear()
        logger.info("Sheets service closed")

    def get_sheet_by_name(self, spreadsheet_id: str, name: str) -> Sheet:
        key = (spreadsheet_id, name)
        sheet = self._sheets.get(key)
        if sheet is None:
            if len(self._sheets) >= SHEETS_CACHE_MAXSIZE:
                oldest_key = next(iter(self._sheets))
                self._sheets.pop(oldest_key).invalidate_cache()
            sheet = Sheet(self, spreadsheet_id, name)
            self._sheets[key] = sheet
        return sheet

    async def get_sheet_by_gid(self, spreadsheet_id: str, gid: int) -> Sheet:
        name = await self.resolve_sheet_name(spreadsheet_id, gid)
        return self.get_sheet_by_name(spreadsheet_id, name)

    def invalidate_all_sheets(self) -> None:
        for sheet in self._sheets.values():
            sheet.invalidate_cache()
        self._sheets.clear()

    async def resolve_sheet_name(self, spreadsheet_id: str, gid: int) -> str:
        for props in await self.list_sheet_properties(spreadsheet_id):
            if props.get("sheetId") != gid:
                continue

            name = str(props.get("title", "")).strip()
            if name:
                return name
            break

        raise SheetNotFoundError(f"Sheet with gid {gid} not found")

    async def resolve_sheet_gid(self, spreadsheet_id: str, sheet_name: str) -> int:
        for props in await self.list_sheet_properties(spreadsheet_id):
            if props.get("title") != sheet_name:
                continue

            sheet_id = props.get("sheetId")
            if isinstance(sheet_id, int):
                return sheet_id

            sheet_id_text = str(sheet_id or "").strip()
            if sheet_id_text.isdigit():
                return int(sheet_id_text)

            raise SheetsAPIError(f"Invalid sheetId for '{sheet_name}'")

        raise SheetNotFoundError(f"Sheet with name '{sheet_name}' not found")

    async def get_rows(self, spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
        result = await self._request(
            lambda: self._service.spreadsheets.values.get(
                spreadsheetId=spreadsheet_id,
                range=sheet_name,
                majorDimension="ROWS",
            )
        )
        return result.get("values", [])

    async def get_header_rows(self, spreadsheet_id: str, sheet_name: str, header_row_count: int) -> list[list[str]]:
        if header_row_count <= 0:
            return []

        result = await self._request(
            lambda: self._service.spreadsheets.values.get(
                spreadsheetId=spreadsheet_id,
                range=f"{_quote_sheet_name(sheet_name)}!1:{header_row_count}",
                majorDimension="ROWS",
            )
        )
        return result.get("values", [])

    async def append_row(self, spreadsheet_id: str, sheet_name: str, values: list[Any]) -> None:
        await self._request(
            lambda: self._service.spreadsheets.values.append(
                spreadsheetId=spreadsheet_id,
                range=sheet_name,
                json={"values": [values]},
                insertDataOption="INSERT_ROWS",
                valueInputOption="USER_ENTERED",
            )
        )

    async def list_sheet_properties(self, spreadsheet_id: str) -> list[dict[str, Any]]:
        result = await self._request(
            lambda: self._service.spreadsheets.get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties",
            )
        )
        sheets = result.get("sheets", [])
        return [sheet.get("properties", {}) for sheet in sheets]

    async def _request(self, call: Callable[[], Any]) -> Any:
        @retry(
            reraise=True,
            stop=stop_after_attempt(MAX_RETRIES + 1),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((SheetsConnectionError, SheetsRateLimitError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),  # type: ignore[invalid-argument-type]
        )
        async def wrapped() -> Any:
            try:
                request = call()
                return await self._aiogoogle.as_service_account(request)
            except Exception as error:  # noqa: BLE001
                raise map_http_error(error)

        return await wrapped()


def _model_headers(model_cls: type[HeaderModel]) -> list[list[str]]:
    headers = getattr(model_cls, "_headers", None)
    if headers is None:
        raise ValueError(f"Model {model_cls.__name__} must define _headers")

    if not isinstance(headers, list) or not headers or not all(isinstance(row, list) for row in headers):
        raise ValueError(f"Model {model_cls.__name__} has invalid _headers format")

    if not all(all(isinstance(cell, str) for cell in row) for row in headers):
        raise ValueError(f"Model {model_cls.__name__} _headers must contain only strings")

    return headers


def _assert_headers_match(
    expected_rows: list[list[str]],
    rows: list[list[str]],
    sheet_name: str,
) -> None:
    header_row_count = len(expected_rows)
    actual_header_rows = rows[:header_row_count]

    mismatches: list[str] = []
    for row_index in range(header_row_count):
        expected_row = expected_rows[row_index] if row_index < len(expected_rows) else []
        actual_row = actual_header_rows[row_index] if row_index < len(actual_header_rows) else []

        if not expected_row:
            continue

        for col_index in range(len(expected_row)):
            expected_value = _normalize_cell(expected_row[col_index])
            actual_value = _normalize_cell(actual_row[col_index] if col_index < len(actual_row) else "")
            if expected_value != actual_value:
                mismatches.append(
                    f"row {row_index + 1}, col {col_index + 1}: expected '{expected_value}' got '{actual_value}'"
                )

    if mismatches:
        details = "; ".join(mismatches)
        raise SheetsSchemaError(f"Header mismatch in '{sheet_name}': {details}")
