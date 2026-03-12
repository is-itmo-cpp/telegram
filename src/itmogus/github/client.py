import logging
from typing import Self

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from itmogus.github.errors import (
    GitHubAPIError,
    GitHubConnectionError,
    GitHubNotFoundError,
    GitHubPermissionError,
    GitHubRateLimitError,
)


logger = logging.getLogger(__name__)

API_URL = "https://api.github.com"
MAX_RETRIES = 3


class GitHubClient:
    def __init__(self, token: str):
        self._token = token
        self._session: ClientSession | None = None

    async def _get_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                base_url=API_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self._token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=ClientTimeout(total=60),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def request(self, method: str, path: str, **kwargs):
        @retry(
            reraise=True,
            stop=stop_after_attempt(MAX_RETRIES + 1),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((GitHubConnectionError, GitHubRateLimitError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),  # type: ignore[invalid-argument-type]
        )
        async def _request():
            session = await self._get_session()
            try:
                resp = await session.request(method, path, **kwargs)
            except ClientError as e:
                logger.warning("GitHub network error: %s %s: %s", method, path, e)
                raise GitHubConnectionError() from e

            # https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api?apiVersion=2026-03-10#exceeding-the-rate-limit
            if resp.status in (403, 429) and resp.headers.get("x-ratelimit-remaining") == "0":
                # TODO: respect x-ratelimit-reset?
                logger.warning("GitHub rate limit exceeded: %s %s", method, path)
                raise GitHubRateLimitError()

            try:
                resp.raise_for_status()
            except ClientResponseError as e:
                if e.status == 404:
                    logger.error("GitHub API not found: %s %s", method, path)
                    raise GitHubNotFoundError() from e
                if e.status == 403:
                    logger.error("GitHub API permission error: %s %s", method, path)
                    raise GitHubPermissionError() from e
                logger.error("GitHub API error: %s %s -> %d", method, path, e.status)
                raise GitHubAPIError() from e
            return resp

        return await _request()
