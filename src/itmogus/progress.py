import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.types import Message


logger = logging.getLogger(__name__)

T = TypeVar("T")


def render_progress_bar(completed: int, total: int, width: int = 20) -> str:
    if width < 1:
        raise ValueError("Progress bar width must be positive")

    ratio = 1.0 if total <= 0 else max(0.0, min(completed / total, 1.0))
    filled = int(width * ratio)
    return f"[{'█' * filled}{'░' * (width - filled)}]"


async def run_with_progress(
    status_message: Message,
    operation: Awaitable[T],
    render: Callable[[], str],
    *,
    interval: float = 1.0,
    parse_mode: str | None = None,
) -> T:
    task = asyncio.ensure_future(operation)
    last_text = render()

    try:
        while True:
            done, _ = await asyncio.wait((task,), timeout=interval)
            if task in done:
                return task.result()

            text = render()
            if text == last_text:
                continue

            last_text = text
            try:
                await status_message.edit_text(text, parse_mode=parse_mode)
            except Exception:
                logger.warning("Failed to update progress message", exc_info=True)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
