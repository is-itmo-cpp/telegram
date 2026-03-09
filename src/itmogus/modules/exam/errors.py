from itmogus.errors import BotError


class ExamError(BotError):
    pass


class ExamConfigError(ExamError):
    user_message = "Ошибка конфигурации экзамена."


class ExamNotConfiguredError(ExamError):
    user_message = "Экзамен не настроен."
