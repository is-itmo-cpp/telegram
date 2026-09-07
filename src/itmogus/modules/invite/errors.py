from enum import Enum


class InviteError(Enum):
    TEMPLATE_NOT_FOUND = "template_not_found"
    TEMPLATE_NOT_PRIVATE = "template_not_private"
    REPO_NOT_FOUND = "repo_not_found"
    INVALID_GITHUB_USERNAME = "invalid_github_username"
    GITHUB_ERROR = "github_error"
    CANCELLED = "cancelled"
