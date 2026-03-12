import asyncio
import logging

from itmogus.core.config import config
from itmogus.github import GitHubClient, GitHubError


logger = logging.getLogger(__name__)

GITHUB_WORKERS = 16


# GitHub does not have any pagination API.
# Repos may get lost if somebody deletes their repo during fetch. Let's just hope that they won't.
async def fetch_repos(github: GitHubClient, org: str, prefix: str) -> list[str]:
    next_page = 1
    max_existing = float("inf")
    repos = []

    async def worker():
        nonlocal next_page, max_existing, repos

        # Optimistic prefetch.
        while next_page <= max_existing:
            page = next_page
            next_page += 1

            resp = await github.request(
                "GET",
                f"/orgs/{org}/repos",
                params={
                    "per_page": 100,
                    "page": page,
                    # asc+created to prevent repos getting lost between pages...
                    "sort": "created",
                    "direction": "asc",
                },
            )
            data = await resp.json()

            if not data:
                max_existing = min(max_existing, page - 1)

            repos.extend(r["name"] for r in data if r["name"].startswith(prefix))

    await asyncio.gather(*(worker() for _ in range(GITHUB_WORKERS)))
    return repos


async def merge_upstream(github: GitHubClient, org: str, repos: list[str], branch: str) -> tuple[int, int]:
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
            except GitHubError as e:
                failed += 1
                logger.warning("Failed to sync repo %s: %s", repo, e)

    await asyncio.gather(*(_worker() for _ in range(GITHUB_WORKERS)))
    return success, failed


async def run_sync(prefix: str) -> tuple[int, int, int]:
    """Run full sync for prefix. Returns (total, success, failed)."""

    async with GitHubClient(config.github_token) as github:
        repos = await fetch_repos(github, config.github_org, prefix)
        total = len(repos)
        success, failed = await merge_upstream(github, config.github_org, repos, config.github_branch)
        return total, success, failed
