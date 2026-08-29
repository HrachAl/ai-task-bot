"""Thin async HTTP client the bot uses to talk to the backend. Keeping the
bot's only external dependency an HTTP call (not a DB session, not a Celery
producer) is what lets it stay a pure Telegram I/O layer."""

import httpx

from app.core.config import get_settings


class BackendError(Exception):
    """Raised when the backend is unreachable or returns an error response."""


class BackendClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def create_text_task(self, *, telegram_id: int, username: str | None, title: str) -> dict:
        return await self._post(
            "/api/tasks",
            {"telegram_id": telegram_id, "username": username, "title": title},
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
        return await self._post(
            "/api/tasks/voice",
            {
                "telegram_id": telegram_id,
                "username": username,
                "telegram_file_id": telegram_file_id,
                "chat_id": chat_id,
                "ack_message_id": ack_message_id,
            },
        )

    async def update_task_status(self, *, task_id: int, status: str) -> dict:
        return await self._patch(f"/api/tasks/{task_id}", {"status": status})

    async def _post(self, path: str, json: dict) -> dict:
        try:
            response = await self._client.post(path, json=json)
        except httpx.HTTPError as exc:
            raise BackendError(f"Backend request to {path} failed") from exc
        return self._handle_response(response, path)

    async def _patch(self, path: str, json: dict) -> dict:
        try:
            response = await self._client.patch(path, json=json)
        except httpx.HTTPError as exc:
            raise BackendError(f"Backend request to {path} failed") from exc
        return self._handle_response(response, path)

    @staticmethod
    def _handle_response(response: httpx.Response, path: str) -> dict:
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
            timeout=settings.telegram_request_timeout_seconds,
        )
    return _client
