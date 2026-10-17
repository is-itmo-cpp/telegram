from enum import Enum


class ReviewConfigError(Enum):
    INVALID_URL = "invalid_url"
    SHEET_NOT_FOUND = "sheet_not_found"
    SCHEMA_MISMATCH = "schema_mismatch"
