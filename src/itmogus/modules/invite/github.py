import logging
from dataclasses import dataclass
from datetime import datetime

from itmogus.core.config import config
from itmogus.github import GitHubClient, GitHubNotFoundError
from itmogus.modules.invite.errors import InviteError
from itmogus.result import Fail, Ok, Result


logger = logging.getLogger(__name__)


@dataclass
class Invitation:
    id: int
    invitee_login: str
    html_url: str
    created_at: datetime
    expired: bool


def _parse_invitation(data: dict) -> Invitation:
    return Invitation(
        id=data["id"],
        invitee_login=data["invitee"]["login"],
        html_url=data["html_url"],
        created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        expired=data.get("expired", False),
    )


async def get_invitations(github: GitHubClient, org: str, repo: str) -> list[Invitation]:
    resp = await github.request("GET", f"/repos/{org}/{repo}/invitations")
    data = await resp.json()
    return [_parse_invitation(item) for item in data]


async def add_collaborator(
    github: GitHubClient,
    org: str,
    repo: str,
    username: str,
    permission: str = "write",
) -> Invitation | None:
    resp = await github.request(
        "PUT",
        f"/repos/{org}/{repo}/collaborators/{username}",
        json={"permission": permission},
    )

    if resp.status == 204:
        return None

    logger.info(
        "Sent invitation to %s for repo %s/%s",
        username,
        config.github_org,
        repo,
    )

    data = await resp.json()
    return _parse_invitation(data)


async def cancel_invitation(github: GitHubClient, org: str, repo: str, invitation_id: int) -> None:
    await github.request("DELETE", f"/repos/{org}/{repo}/invitations/{invitation_id}")


async def get_user_invitation(
    github: GitHubClient,
    org: str,
    repo: str,
    github_username: str,
) -> Invitation | None:
    invitations = await get_invitations(github, org, repo)
    for inv in invitations:
        if inv.invitee_login.lower() == github_username.lower():
            return inv
    return None


async def ensure_invitation(
    repo: str,
    github_username: str,
) -> Result[tuple[Invitation, bool], InviteError]:
    try:
        async with GitHubClient(config.github_token) as github:
            existing = await get_user_invitation(github, config.github_org, repo, github_username)

            if existing is not None:
                if not existing.expired:
                    return Ok((existing, False))
                await cancel_invitation(github, config.github_org, repo, existing.id)

            new_inv = await add_collaborator(github, config.github_org, repo, github_username)
            if new_inv is None:
                return Fail(InviteError.ALREADY_HAS_ACCESS)

            return Ok((new_inv, True))
    except GitHubNotFoundError:
        logger.warning("Repository not found: %s/%s", config.github_org, repo)
        return Fail(InviteError.REPO_NOT_FOUND)
