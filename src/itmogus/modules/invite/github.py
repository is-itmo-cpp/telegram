import logging
from dataclasses import dataclass
from datetime import datetime

from itmogus.core.config import config
from itmogus.github import GitHubClient, GitHubError, GitHubNotFoundError
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

    @classmethod
    def parse(cls, data: dict) -> Self:
        return cls(
            id=data["id"],
            invitee_login=data["invitee"]["login"],
            html_url=data["html_url"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            expired=data.get("expired", False),
        )


class EnsureStatus:
    @dataclass
    class RepoExists:
        url: str

    @dataclass
    class InvitationCreated:
        invitation: Invitation

    @dataclass
    class InvitationExists:
        invitation: Invitation


async def get_repo_visibility(github: GitHubClient, org: str, repo: str) -> str | None:
    try:
        resp = await github.request("GET", f"/repos/{org}/{repo}")
        data = await resp.json()
        return data.get("visibility")
    except GitHubNotFoundError:
        return None


async def fork_repo(
    github: GitHubClient,
    template_org: str,
    template_repo: str,
    target_org: str,
    target_name: str,
) -> bool:
    try:
        resp = await github.request(
            "POST",
            f"/repos/{template_org}/{template_repo}/forks",
            json={
                "organization": target_org,
                "name": target_name,
                "default_branch_only": True,
            },
        )
        return resp.status == 202
    except GitHubError:
        return False


async def get_invitations(github: GitHubClient, org: str, repo: str) -> list[Invitation]:
    resp = await github.request("GET", f"/repos/{org}/{repo}/invitations")
    data = await resp.json()
    return [Invitation.parse(item) for item in data]


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
    return Invitation.parse(data)


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


def _get_template_name(template_name: str) -> str:
    return f"{config.github_classroom}-{template_name}-{template_name}"


def _get_repo_name(template_name: str, github_username: str) -> str:
    return f"{template_name}-{github_username}"


async def ensure_invitation(
    template_name: str,
    github_username: str,
) -> Result[EnsureStatus, InviteError]:
    repo = _get_repo_name(template_name, github_username)

    try:
        async with GitHubClient(config.github_token) as github:
            visibility = await get_repo_visibility(github, config.github_org, repo)

            if visibility is None:
                template = _get_template_name(template_name)
                template_visibility = await get_repo_visibility(github, config.github_org, template)

                if template_visibility is None:
                    logger.warning("Template not found: %s/%s", config.github_org, template)
                    return Fail(InviteError.TEMPLATE_NOT_FOUND)

                if template_visibility != "private":
                    logger.warning("Template is not private: %s/%s", config.github_org, template)
                    return Fail(InviteError.TEMPLATE_NOT_PRIVATE)

                success = await fork_repo(
                    github,
                    config.github_org,
                    template,
                    config.github_org,
                    repo,
                )
                if not success:
                    logger.warning("Failed to fork template: %s -> %s", template, repo)
                    return Fail(InviteError.FORK_FAILED)

                logger.info("Forked template %s -> %s", template, repo)

            existing = await get_user_invitation(github, config.github_org, repo, github_username)

            if existing is not None:
                if not existing.expired:
                    return Ok(EnsureStatus.InvitationExists(existing))
                await cancel_invitation(github, config.github_org, repo, existing.id)

            new_inv = await add_collaborator(github, config.github_org, repo, github_username)
            if new_inv is None:
                repo = f"https://github.com/{config.github_org}/{repo}"
                return Ok(EnsureStatus.RepoExists(repo))

            return Ok(EnsureStatus.InvitationCreated(new_inv))
    except GitHubError:
        logger.exception("GitHub error during invitation")
        return Fail(InviteError.FORK_FAILED)
