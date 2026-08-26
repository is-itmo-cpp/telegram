import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Self

from itmogus.core.config import config
from itmogus.github import GitHubClient, GitHubError, GitHubNotFoundError
from itmogus.labs import get_student_repo_name, get_template_repo_name
from itmogus.modules.invite.errors import InviteError
from itmogus.result import Fail, Ok, Result


logger = logging.getLogger(__name__)

GITHUB_WORKERS = 16


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


type EnsureResult = EnsureStatus.RepoExists | EnsureStatus.InvitationCreated | EnsureStatus.InvitationExists


class RolloutPhase(Enum):
    CHECKING_TEMPLATE = "checking_template"
    LISTING_FORKS = "listing_forks"
    CREATING_FORKS = "creating_forks"
    SENDING_INVITATIONS = "sending_invitations"


@dataclass
class RolloutProgress:
    phase: RolloutPhase = RolloutPhase.CHECKING_TEMPLATE
    students: int = 0
    github_accounts: int = 0
    missing_github: int = 0
    duplicate_github: int = 0
    total: int = 0
    completed: int = 0
    forks_found: int = 0
    forks_existing: int = 0
    forks_created: int = 0
    fork_errors: int = 0
    invitations_sent: int = 0
    already_accessible: int = 0
    invitation_errors: int = 0


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


async def run_rollout(
    template_name: str,
    github_usernames: list[str],
    progress: RolloutProgress,
) -> InviteError | None:
    template_repo = get_template_repo_name(template_name)

    async with GitHubClient(config.github_token) as github:
        # Phase 0. Change visibility
        visibility = await get_repo_visibility(github, config.github_org, template_repo)
        if visibility is None:
            return InviteError.TEMPLATE_NOT_FOUND
        if visibility != "private":
            return InviteError.TEMPLATE_NOT_PRIVATE

        # Phase 1. Collect students & forks
        progress.phase = RolloutPhase.LISTING_FORKS
        existing_forks = set()
        async for page in github.paginate(
            f"/repos/{config.github_org}/{template_repo}/forks",
            params={"sort": "oldest"},
        ):
            existing_forks.update(repo["name"].casefold() for repo in page)
            progress.forks_found += len(page)

        missing_forks = [
            username
            for username in github_usernames
            if get_student_repo_name(template_name, username).casefold() not in existing_forks
        ]
        progress.forks_existing = len(github_usernames) - len(missing_forks)
        progress.phase = RolloutPhase.CREATING_FORKS
        progress.total = len(github_usernames)
        progress.completed = progress.forks_existing

        # Phase 2. Create missing forks
        async def fork_worker() -> None:
            while missing_forks:
                username = missing_forks.pop()
                repo = get_student_repo_name(template_name, username)
                success = await fork_repo(
                    github,
                    config.github_org,
                    template_repo,
                    config.github_org,
                    repo,
                )
                if success:
                    progress.forks_created += 1
                    logger.info("Forked template %s -> %s", template_repo, repo)
                else:
                    progress.fork_errors += 1
                    logger.warning("Failed to fork template: %s -> %s", template_repo, repo)
                progress.completed += 1

        await asyncio.gather(*(fork_worker() for _ in range(GITHUB_WORKERS)))

        # Phase 3. Send invitations
        pending_invitations = github_usernames.copy()
        progress.phase = RolloutPhase.SENDING_INVITATIONS
        progress.total = len(pending_invitations)
        progress.completed = 0

        async def invitation_worker() -> None:
            while pending_invitations:
                username = pending_invitations.pop()
                repo = get_student_repo_name(template_name, username)
                try:
                    invitation = await add_collaborator(github, config.github_org, repo, username)
                    if invitation is None:
                        progress.already_accessible += 1
                    else:
                        progress.invitations_sent += 1
                except GitHubError:
                    progress.invitation_errors += 1
                    logger.warning("Failed to invite %s to %s", username, repo)
                progress.completed += 1

        await asyncio.gather(*(invitation_worker() for _ in range(GITHUB_WORKERS)))

    return None


async def ensure_invitation(
    template_name: str,
    github_username: str,
) -> Result[EnsureResult, InviteError]:
    repo = get_student_repo_name(template_name, github_username)

    try:
        async with GitHubClient(config.github_token) as github:
            visibility = await get_repo_visibility(github, config.github_org, repo)

            if visibility is None:
                template = get_template_repo_name(template_name)
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
