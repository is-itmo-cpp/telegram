import aiohttp

from itmogus.errors import BotError


class SheetsError(BotError):
    pass


class SheetsConnectionError(SheetsError):
    pass


class SheetsRateLimitError(SheetsError):
    pass


class SheetsAuthError(SheetsError):
    pass


class SheetNotFoundError(SheetsError):
    pass


class SheetsAPIError(SheetsError):
    pass


class SheetsSchemaError(SheetsError):
    pass


def map_http_error(error: Exception) -> SheetsError:
    message = str(error)

    if isinstance(error, aiohttp.ClientError):
        return SheetsConnectionError(f"Connection error: {message}")

    lowered = message.lower()
    if "http" in lowered and "error" in lowered:
        if "401" in lowered or "403" in lowered:
            return SheetsAuthError(f"Auth error: {message}")
        if "404" in lowered:
            return SheetNotFoundError(f"Not found: {message}")
        if "429" in lowered:
            return SheetsRateLimitError(f"Rate limited: {message}")
        if any(code in lowered for code in ("500", "502", "503")):
            return SheetsAPIError(f"Server error: {message}")

    return SheetsAPIError(f"Unknown error: {message}")
