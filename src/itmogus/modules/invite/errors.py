from enum import Enum


class InviteError(Enum):
    TEMPLATE_NOT_FOUND = "template_not_found"
    TEMPLATE_NOT_PRIVATE = "template_not_private"
    FORK_FAILED = "fork_failed"
