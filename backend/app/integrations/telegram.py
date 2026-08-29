"""Minimal synchronous Telegram Bot API client used by the Celery worker.

The worker runs in a separate process from the aiogram bot, so it cannot reuse
the bot's own `Bot` instance — it talks to the Telegram HTTP API directly with
a plain `httpx` client, using only the handful of methods it needs:
downloading a voice file and sending/editing a confirmation message.
"""

import httpx

from app.core.config import get_settings
from app.exceptions import AudioDownloadError, TelegramAPIError


class TelegramClient:
    def __init__(self, token: str, base_url: str, timeout: float) -> None:
        self._api_url = f"{base_url}/bot{token}"
        self._file_url = f"{base_url}/file/bot{token}"
        self._timeout = timeout

    def _call(self, method: str, payload: dict) -> dict:
        try:
            response = httpx.post(f"{self._api_url}/{method}", json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise TelegramAPIError(f"Telegram API request failed: {method}") from exc

        if response.status_code != 200:
            raise TelegramAPIError(
                f"Telegram API error {response.status_code} for {method}: {response.text[:200]}"
            )

        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(f"Telegram API returned not-ok for {method}: {data}")
        return data["result"]

    def get_file_path(self, file_id: str) -> str:
        try:
            result = self._call("getFile", {"file_id": file_id})
        except TelegramAPIError as exc:
            raise AudioDownloadError(f"Could not locate voice file on Telegram: {exc}") from exc
        return result["file_path"]

    def download_file(self, file_path: str) -> bytes:
        url = f"{self._file_url}/{file_path}"
        try:
            response = httpx.get(url, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise AudioDownloadError("Failed to download voice file from Telegram") from exc

        if response.status_code != 200:
            raise AudioDownloadError(f"Telegram file download failed: HTTP {response.status_code}")
        return response.content

    def send_message(self, chat_id: int, text: str, *, reply_markup: dict | None = None) -> dict:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._call("sendMessage", payload)

    def edit_message_text(
        self, chat_id: int, message_id: int, text: str, *, reply_markup: dict | None = None
    ) -> dict:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._call("editMessageText", payload)


def get_telegram_client() -> TelegramClient:
    settings = get_settings()
    return TelegramClient(
        token=settings.telegram_bot_token,
        base_url=settings.telegram_api_base_url,
        timeout=settings.telegram_request_timeout_seconds,
    )
