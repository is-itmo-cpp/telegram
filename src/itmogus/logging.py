import json
import logging
import re
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message


current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
current_event_id: ContextVar[str | None] = ContextVar("current_event_id", default=None)


RE_AIOGRAM_UNHANDLED = re.compile(r"^Update id=\d+ is not handled\.")
RE_AIOGRAM_HANDLED = re.compile(r"^Update id=\d+.*is handled")


class AiogramEventFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "aiogram.event":
            return True

        if RE_AIOGRAM_UNHANDLED.match(record.getMessage()):
            return False

        if RE_AIOGRAM_HANDLED.match(record.getMessage()):
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"

        return True


def generate_event_id() -> str:
    return str(uuid4())


class ContextMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        event_id = generate_event_id()
        current_event_id.set(event_id)

        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            current_user_id.set(user_id)

        return await handler(event, data)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.user_id = current_user_id.get()
        record.event_id = current_event_id.get()
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        event_id = getattr(record, "event_id", None)
        if event_id:
            log_data["event_id"] = event_id

        user_id = getattr(record, "user_id", None)
        if user_id:
            log_data["user_id"] = user_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    context_filter = ContextFilter()
    aiogram_filter = AiogramEventFilter()

    file_handler = RotatingFileHandler(
        log_dir / "itmogus.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    file_handler.addFilter(context_filter)
    file_handler.addFilter(aiogram_filter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(JSONFormatter())
    console_handler.addFilter(context_filter)
    console_handler.addFilter(aiogram_filter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
