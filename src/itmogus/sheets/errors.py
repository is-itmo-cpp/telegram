import aiohttp

from itmogus.errors import BotError


class SheetsError(BotError):
    pass


class SheetsConnectionError(SheetsError):
    user_message = "Ошибка подключения к Google. Попробуйте позже."


class SheetsRateLimitError(SheetsError):
    user_message = "Слишком много запросов. Попробуйте позже."


class SheetsAuthError(SheetsError):
    user_message = "Нет доступа к таблице. Обратитесь к администратору."


class SheetNotFoundError(SheetsError):
    user_message = "Таблица или лист не найден."


class SheetsAPIError(SheetsError):
    user_message = "Ошибка API Google."


class SheetsSchemaError(SheetsError):
    user_message = "Неверная структура листа."


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
