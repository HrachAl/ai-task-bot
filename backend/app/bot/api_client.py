"""Thin async HTTP client the bot uses to talk to the backend. Keeping the
bot's only external dependency an HTTP call (not a DB session, not a Celery
producer) is what lets it stay a pure Telegram I/O layer.

Every call is made *on behalf of* a Telegram user: the bot proves it is the
trusted internal service with a shared secret, and names the user it is
acting for. The backend resolves that pair into a real user account, so the
bot never has to know or cache anyone's personal dashboard token.
"""

import httpx

from app.core.config import get_settings


class BackendError(Exception):
    """Raised when the backend is unreachable or returns an error response."""


class BackendClient:
    def __init__(self, base_url: str, internal_token: str, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._internal_token = internal_token

    async def close(self) -> None:
        await self._client.aclose()

    def _auth_headers(self, telegram_id: int, username: str | None) -> dict[str, str]:
        headers = {
            "X-Internal-Token": self._internal_token,
            "X-Telegram-Id": str(telegram_id),
        }
        if username:
            headers["X-Telegram-Username"] = username
        return headers

    async def create_text_task(self, *, telegram_id: int, username: str | None, title: str) -> dict:
        return await self._request(
            "POST", "/api/tasks", telegram_id, username, json={"title": title}
        )

    async def enqueue_voice_task(
        self,
        *,
        telegram_id: int,
        username: str | None,
        telegram_file_id: str,
        chat_id: int,
        ack_message_id: int | None,
    ) -> dict:
        return await self._request(
            "POST",
            "/api/tasks/voice",
            telegram_id,
            username,
            json={
                "telegram_file_id": telegram_file_id,
                "chat_id": chat_id,
                "ack_message_id": ack_message_id,
            },
        )

    async def list_tasks(self, *, telegram_id: int, username: str | None) -> list[dict]:
        return await self._request("GET", "/api/tasks", telegram_id, username)

    async def get_task(self, *, telegram_id: int, username: str | None, task_id: int) -> dict:
        return await self._request("GET", f"/api/tasks/{task_id}", telegram_id, username)

    async def update_task_status(
        self, *, telegram_id: int, username: str | None, task_id: int, status: str
    ) -> dict:
        return await self._request(
            "PATCH", f"/api/tasks/{task_id}", telegram_id, username, json={"status": status}
        )

    async def get_me(self, *, telegram_id: int, username: str | None) -> dict:
        return await self._request("GET", "/api/me", telegram_id, username)

    async def _request(
        self,
        method: str,
        path: str,
        telegram_id: int,
        username: str | None,
        *,
        json: dict | None = None,
    ):
        try:
            response = await self._client.request(
                method, path, json=json, headers=self._auth_headers(telegram_id, username)
            )
        except httpx.HTTPError as exc:
            raise BackendError(f"Backend request to {path} failed") from exc
        return self._handle_response(response, path)

    @staticmethod
    def _handle_response(response: httpx.Response, path: str):
        if response.status_code >= 400:
            raise BackendError(
                f"Backend returned {response.status_code} for {path}: {response.text[:200]}"
            )
        return response.json()


_client: BackendClient | None = None


def get_backend_client() -> BackendClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = BackendClient(
            base_url=settings.backend_internal_url,
            internal_token=settings.internal_api_token,
            timeout=settings.telegram_request_timeout_seconds,
        )
    return _client
