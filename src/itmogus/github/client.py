import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any, Self

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from itmogus.core.config import config
from itmogus.github.auth import GitHubAppAuth
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
PAGE_SIZE = 100

# https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api?apiVersion=2026-03-10#handle-rate-limit-errors-appropriately
MAX_RATE_LIMIT_RETRIES = 5
MAX_RATE_LIMIT_WAIT = 30 * 60
DEFAULT_RATE_LIMIT_WAIT = 60
RATE_LIMIT_STATUSES = (403, 422, 429)
RATE_LIMIT_PHRASES = ("rate limit", "too quickly", "abuse")


async def _error_message(resp: ClientResponse) -> str:
    text = await resp.text()
    try:
        data = json.loads(text)
    except ValueError:
        return text[:200]
    if not isinstance(data, dict):
        return text[:200]
    parts = [str(data.get("message", ""))]
    for error in data.get("errors", []):
        if isinstance(error, dict) and "message" in error:
            parts.append(str(error["message"]))
        elif isinstance(error, str):
            parts.append(error)
    return "; ".join(part for part in parts if part) or text[:200]


async def _rate_limit_delay(resp: ClientResponse) -> float | None:
    if resp.status not in RATE_LIMIT_STATUSES:
        return None

    retry_after = resp.headers.get("retry-after")
    if retry_after is not None:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            return DEFAULT_RATE_LIMIT_WAIT

    if resp.headers.get("x-ratelimit-remaining") == "0":
        try:
            return max(int(resp.headers["x-ratelimit-reset"]) - time.time(), 1.0)
        except KeyError, ValueError:
            return DEFAULT_RATE_LIMIT_WAIT

    if resp.status == 429:
        return DEFAULT_RATE_LIMIT_WAIT

    message = (await _error_message(resp)).lower()
    if any(phrase in message for phrase in RATE_LIMIT_PHRASES):
        return DEFAULT_RATE_LIMIT_WAIT

    return None


_default_auth: GitHubAppAuth | None = None


def default_auth() -> GitHubAppAuth:
    global _default_auth
    if _default_auth is None:
        _default_auth = GitHubAppAuth.from_key_file(
            config.github_app_id,
            config.github_app_private_key_path,
            config.github_org,
        )
    return _default_auth


class GitHubClient:
    def __init__(self, auth: GitHubAppAuth | None = None):
        self._auth = auth or default_auth()
        self._session: ClientSession | None = None

    async def _get_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                base_url=API_URL,
                headers={
                    "Accept": "application/vnd.github+json",
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

    @retry(
        reraise=True,
        stop=stop_after_attempt(MAX_RETRIES + 1),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(GitHubConnectionError),
        before_sleep=before_sleep_log(logger, logging.WARNING),  # type: ignore[invalid-argument-type]
    )
    async def _send(self, method: str, path: str, **kwargs) -> ClientResponse:
        session = await self._get_session()
        token = await self._auth.token(session)
        headers = {**kwargs.pop("headers", {}), "Authorization": f"Bearer {token}"}
        try:
            return await session.request(method, path, headers=headers, **kwargs)
        except ClientError as e:
            logger.warning("GitHub network error: %s %s: %s", method, path, e)
            raise GitHubConnectionError() from e

    async def request(self, method: str, path: str, **kwargs) -> ClientResponse:
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            resp = await self._send(method, path, **kwargs)

            delay = await _rate_limit_delay(resp)
            if delay is None:
                return await self._check(resp, method, path)

            if attempt == MAX_RATE_LIMIT_RETRIES or delay > MAX_RATE_LIMIT_WAIT:
                logger.error("GitHub rate limit exceeded: %s %s (would wait %.0fs)", method, path, delay)
                raise GitHubRateLimitError()

            logger.warning("GitHub rate limit hit: %s %s, retrying in %.0fs", method, path, delay)
            await asyncio.sleep(delay)

        raise GitHubRateLimitError()

    async def _check(self, resp: ClientResponse, method: str, path: str) -> ClientResponse:
        if resp.status < 400:
            return resp

        message = await _error_message(resp)
        if resp.status == 404:
            logger.error("GitHub API not found: %s %s: %s", method, path, message)
            raise GitHubNotFoundError()
        if resp.status == 403:
            logger.error("GitHub API permission error: %s %s: %s", method, path, message)
            raise GitHubPermissionError()
        logger.error("GitHub API error: %s %s -> %d: %s", method, path, resp.status, message)
        raise GitHubAPIError()

    # GitHub does not have any pagination API.
    # Something may get lost if it's modified during fetch. Let's just hope that it won't.
    async def paginate(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        page = 1
        base_params = dict(params or {})

        while True:
            response = await self.request(
                "GET",
                path,
                params={**base_params, "per_page": PAGE_SIZE, "page": page},
            )
            items = await response.json()
            if not items:
                return

            yield items

            if len(items) < PAGE_SIZE:
                return
            page += 1
