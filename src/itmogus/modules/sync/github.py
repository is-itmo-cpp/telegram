import asyncio
import logging
from contextlib import asynccontextmanager

from aiohttp import ClientSession, ClientTimeout

from itmogus.core.config import config


logger = logging.getLogger(__name__)

API_URL = "https://api.github.com"
GITHUB_WORKERS = 16


@asynccontextmanager
async def make_client():
    async with ClientSession(
        base_url=API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {config.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=ClientTimeout(total=60),
    ) as client:
        yield client


# GitHub does not have any pagination API.
# Repos may get lost if somebody deletes their repo during fetch. Let's just hope that they won't.
async def fetch_repos(client: ClientSession, org: str, prefix: str) -> list[str]:
    next_page = 1
    max_existing = float("inf")
    repos = []

    async def worker():
        nonlocal next_page, max_existing, repos

        # Optimistic prefetch.
        while next_page <= max_existing:
            page = next_page
            next_page += 1

            resp = await client.get(
                f"/orgs/{org}/repos",
                params={
                    "per_page": 100,
                    "page": page,
                    # asc+created to prevent repos getting lost between pages...
                    "sort": "created",
                    "direction": "asc",
                },
            )
            resp.raise_for_status()
            data = await resp.json()

            if not data:
                max_existing = min(max_existing, page - 1)

            repos.extend(r["name"] for r in data if r["name"].startswith(prefix))

    await asyncio.gather(*(worker() for _ in range(GITHUB_WORKERS)))
    return repos


async def merge_upstream(client: ClientSession, org: str, repos: list[str], branch: str) -> tuple[int, int]:
    success = 0
    failed = 0

    async def _worker():
        nonlocal success, failed
        while repos:
            repo = repos.pop()

            resp = await client.post(
                f"/repos/{org}/{repo}/merge-upstream",
                json={"branch": branch},
            )

            data = await resp.json()

            if resp.ok:
                success += 1
            else:
                failed += 1
                logger.warning("Failed to sync repo %s: %s", repo, data.get("message"))

    await asyncio.gather(*(_worker() for _ in range(GITHUB_WORKERS)))
    return success, failed


async def run_sync(prefix: str) -> tuple[int, int, int]:
    """Run full sync for prefix. Returns (total, success, failed)."""
    async with make_client() as client:
        repos = await fetch_repos(client, config.github_org, prefix)
        total = len(repos)
        success, failed = await merge_upstream(client, config.github_org, repos, config.github_branch)
        return total, success, failed
