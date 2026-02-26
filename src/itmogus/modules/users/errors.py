from itmogus.errors import BotError


class UsersError(BotError):
    pass


class TelegramAlreadyBoundError(UsersError):
    pass


class IsuAlreadyBoundError(UsersError):
    pass


class NoSuchIsuError(UsersError):
    pass
