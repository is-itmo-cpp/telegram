from itmogus.errors import InfraError


class GitHubError(InfraError):
    pass


class GitHubConnectionError(GitHubError):
    user_message = "Ошибка подключения к GitHub. Попробуйте позже."


class GitHubRateLimitError(GitHubError):
    user_message = "Слишком много запросов к GitHub. Попробуйте позже."


class GitHubAPIError(GitHubError):
    user_message = "Ошибка при обращении к GitHub API."


class GitHubPermissionError(GitHubError):
    user_message = "Недостаточно прав для выполнения операции в GitHub."


class GitHubNotFoundError(GitHubError):
    user_message = "Ресурс не найден в GitHub."
