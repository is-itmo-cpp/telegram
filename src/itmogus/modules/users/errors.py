from itmogus.errors import BotError


class UsersError(BotError):
    pass


class TelegramAlreadyBoundError(UsersError):
    user_message = "Этот Telegram уже привязан к другому ИСУ."


class IsuAlreadyBoundError(UsersError):
    user_message = "Этот ИСУ уже привязан к другому Telegram."


class NoSuchIsuError(UsersError):
    user_message = "Студент с таким ИСУ не найден."
