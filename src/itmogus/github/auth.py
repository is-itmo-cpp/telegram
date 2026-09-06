import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

import jwt
from aiohttp import ClientError, ClientSession

from itmogus.github.errors import GitHubAuthError, GitHubConnectionError


logger = logging.getLogger(__name__)

JWT_LIFETIME = 9 * 60
JWT_BACKDATE = 60
TOKEN_REFRESH_MARGIN = 5 * 60


class GitHubAppAuth:
    def __init__(self, app_id: int, private_key: str, org: str):
        self._app_id = app_id
        self._private_key = private_key
        self._org = org
        self._installation_id: int | None = None
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    @classmethod
    def from_key_file(cls, app_id: int, private_key_path: str | Path, org: str) -> "GitHubAppAuth":
        return cls(app_id, Path(private_key_path).read_text(), org)

    def _app_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - JWT_BACKDATE, "exp": now + JWT_LIFETIME, "iss": str(self._app_id)}
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    async def token(self, session: ClientSession) -> str:
        if self._token is not None and time.time() < self._expires_at - TOKEN_REFRESH_MARGIN:
            return self._token

        async with self._lock:
            if self._token is not None and time.time() < self._expires_at - TOKEN_REFRESH_MARGIN:
                return self._token
            await self._refresh(session)
            assert self._token is not None
            return self._token

    async def _refresh(self, session: ClientSession) -> None:
        headers = {"Authorization": f"Bearer {self._app_jwt()}"}

        if self._installation_id is None:
            data = await self._call(session, "GET", f"/orgs/{self._org}/installation", headers)
            self._installation_id = int(data["id"])
            logger.info("Resolved GitHub App installation %d for org %s", self._installation_id, self._org)

        data = await self._call(
            session,
            "POST",
            f"/app/installations/{self._installation_id}/access_tokens",
            headers,
        )
        self._token = data["token"]
        self._expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
        logger.info("Obtained GitHub App installation token, valid until %s", data["expires_at"])

    async def _call(self, session: ClientSession, method: str, path: str, headers: dict[str, str]) -> dict:
        try:
            resp = await session.request(method, path, headers=headers)
        except ClientError as e:
            logger.warning("GitHub network error: %s %s: %s", method, path, e)
            raise GitHubConnectionError() from e

        if resp.status >= 400:
            body = (await resp.text())[:300]
            logger.error("GitHub App auth failed: %s %s -> %d: %s", method, path, resp.status, body)
            # Installation lookup 404 means the app is not installed on the org.
            self._installation_id = None
            raise GitHubAuthError()

        return await resp.json()
