import asyncio
import logging
from dataclasses import dataclass

from itmogus.core.config import config
from itmogus.github import GitHubClient, GitHubError
from itmogus.labs import get_template_repo_name


logger = logging.getLogger(__name__)

GITHUB_WORKERS = 16


@dataclass
class SyncProgress:
    found: int = 0
    total: int | None = None
    success: int = 0
    failed: int = 0

    @property
    def completed(self) -> int:
        return self.success + self.failed


async def fetch_forks(
    github: GitHubClient,
    org: str,
    template_repo: str,
    progress: SyncProgress | None = None,
) -> list[str]:
    repos = []

    async for page in github.paginate(
        f"/repos/{org}/{template_repo}/forks",
        params={"sort": "oldest"},
    ):
        repos.extend(repo["name"] for repo in page)
        if progress is not None:
            progress.found += len(page)

    return repos


async def merge_upstream(
    github: GitHubClient,
    org: str,
    repos: list[str],
    branch: str,
    progress: SyncProgress | None = None,
) -> tuple[int, int]:
    success = 0
    failed = 0

    async def _worker():
        nonlocal success, failed
        while repos:
            repo = repos.pop()

            try:
                await github.request(
                    "POST",
                    f"/repos/{org}/{repo}/merge-upstream",
                    json={"branch": branch},
                )
                success += 1
                if progress is not None:
                    progress.success += 1
            except GitHubError as e:
                failed += 1
                if progress is not None:
                    progress.failed += 1
                logger.warning("Failed to sync repo %s: %s", repo, e)

    await asyncio.gather(*(_worker() for _ in range(GITHUB_WORKERS)))
    return success, failed


async def run_sync(lab_name: str, progress: SyncProgress | None = None) -> tuple[int, int, int]:
    """Run full sync for a lab. Returns (total, success, failed)."""

    template_repo = get_template_repo_name(lab_name)

    async with GitHubClient(config.github_token) as github:
        repos = await fetch_forks(github, config.github_org, template_repo, progress)
        total = len(repos)
        if progress is not None:
            progress.total = total
        success, failed = await merge_upstream(
            github,
            config.github_org,
            repos,
            config.github_branch,
            progress,
        )
        return total, success, failed
