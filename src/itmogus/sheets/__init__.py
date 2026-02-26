from pydantic import BaseModel

from itmogus.sheets.errors import (
    SheetNotFoundError,
    SheetsAPIError,
    SheetsAuthError,
    SheetsConnectionError,
    SheetsError,
    SheetsRateLimitError,
    SheetsSchemaError,
)
from itmogus.sheets.sheet import Sheet, SheetsClient
from itmogus.sheets.url import parse_sheets_url


class SheetRef(BaseModel):
    spreadsheet_id: str = ""
    sheet_name: str = ""


def cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def parse_int(value: str) -> int | None:
    text = value.strip()
    if not text or not text.isdigit():
        return None
    return int(text)


__all__ = [
    "Sheet",
    "SheetRef",
    "SheetsClient",
    "cell",
    "parse_int",
    "parse_sheets_url",
    "SheetsError",
    "SheetsConnectionError",
    "SheetsRateLimitError",
    "SheetsAuthError",
    "SheetNotFoundError",
    "SheetsAPIError",
    "SheetsSchemaError",
]
