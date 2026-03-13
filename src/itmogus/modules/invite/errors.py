from enum import Enum


class InviteError(Enum):
    NOT_REGISTERED = "not_registered"
    NO_GITHUB = "no_github"
    ALREADY_HAS_ACCESS = "already_has_access"
    REPO_NOT_FOUND = "repo_not_found"
