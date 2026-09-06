import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware, Dispatcher
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, TelegramObject


logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 15 * 60

CONFIRM = "confirm"
CANCEL = "cancel"

STALE_MESSAGE = "⌛ Кнопка устарела или уже была нажата. Повторите команду."
FOREIGN_MESSAGE = "Эта кнопка предназначена другому пользователю."


class ActionCallback(CallbackData, prefix="act"):
    token: str
    choice: str = ""


@dataclass(frozen=True)
class Ticket:
    owner_id: int
    payload: Any
    expires_at: float


class PendingActions:
    def __init__(self, ttl: float = DEFAULT_TTL_SECONDS):
        self._ttl = ttl
        self._tickets: dict[str, Ticket] = {}

    def create(self, owner_id: int, payload: Any, ttl: float | None = None) -> str:
        self._purge()
        token = secrets.token_urlsafe(12)
        expires_at = time.monotonic() + (self._ttl if ttl is None else ttl)
        self._tickets[token] = Ticket(owner_id=owner_id, payload=payload, expires_at=expires_at)
        return token

    def peek(self, token: str) -> Ticket | None:
        ticket = self._tickets.get(token)
        if ticket is None:
            return None
        if ticket.expires_at <= time.monotonic():
            del self._tickets[token]
            return None
        return ticket

    def consume(self, token: str) -> Ticket | None:
        ticket = self.peek(token)
        if ticket is not None:
            del self._tickets[token]
        return ticket

    def _purge(self) -> None:
        now = time.monotonic()
        for token in [token for token, ticket in self._tickets.items() if ticket.expires_at <= now]:
            del self._tickets[token]

    def __len__(self) -> int:
        self._purge()
        return len(self._tickets)


def action_button(text: str, token: str, choice: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=ActionCallback(token=token, choice=choice).pack())


def parse_action(callback_data: str | None) -> ActionCallback | None:
    if not callback_data:
        return None
    try:
        return ActionCallback.unpack(callback_data)
    except ValueError, TypeError:
        return None


async def remove_keyboard(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


class ActionGate(BaseMiddleware):
    def __init__(self, actions: PendingActions):
        self.actions = actions

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        action = parse_action(event.data)
        if action is None:
            return await handler(event, data)

        ticket = self.actions.peek(action.token)
        if ticket is None:
            logger.info("Rejected stale action token from user %d", event.from_user.id)
            await event.answer(STALE_MESSAGE)
            await remove_keyboard(event)
            return UNHANDLED

        if event.from_user.id != ticket.owner_id:
            logger.warning(
                "User %d pressed a button owned by user %d (%s)",
                event.from_user.id,
                ticket.owner_id,
                type(ticket.payload).__name__,
            )
            await event.answer(FOREIGN_MESSAGE, show_alert=True)
            return UNHANDLED

        self.actions.consume(action.token)

        data["payload"] = ticket.payload
        data["choice"] = action.choice
        return await handler(event, data)


class Action(BaseFilter):
    def __init__(self, payload_type: type):
        self.payload_type = payload_type

    async def __call__(self, event: TelegramObject, payload: Any = None) -> bool:
        return isinstance(payload, self.payload_type)


def setup_actions(dp: Dispatcher, ttl: float = DEFAULT_TTL_SECONDS) -> PendingActions:
    actions = PendingActions(ttl=ttl)
    dp.workflow_data["actions"] = actions
    dp.callback_query.outer_middleware(ActionGate(actions))
    return actions
