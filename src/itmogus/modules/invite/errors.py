from enum import Enum


class InviteError(Enum):
    NOT_REGISTERED = "not_registered"
    NO_GITHUB = "no_github"
    ALREADY_HAS_ACCESS = "already_has_access"
    TEMPLATE_NOT_FOUND = "template_not_found"
    TEMPLATE_NOT_PRIVATE = "template_not_private"
    FORK_FAILED = "fork_failed"
