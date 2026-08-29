from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from kombu.exceptions import OperationalError

from app.api import tasks as tasks_api


@pytest.fixture(autouse=True)
def fake_delay(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(tasks_api.transcribe_voice_task, "delay", mock)
    return mock


class TestCreateVoiceTaskEndpoint:
    async def test_returns_202_and_queued_status(self, client: AsyncClient, fake_delay):
        response = await client.post(
            "/api/tasks/voice",
            json={
                "telegram_id": 1,
                "username": "hrach",
                "telegram_file_id": "AwACAgIA",
                "chat_id": 1,
                "ack_message_id": 5,
            },
        )
        assert response.status_code == 202
        assert response.json() == {"status": "queued"}

    async def test_enqueues_with_correct_arguments(self, client: AsyncClient, fake_delay):
        await client.post(
            "/api/tasks/voice",
            json={
                "telegram_id": 42,
                "username": "hrach",
                "telegram_file_id": "file-xyz",
                "chat_id": 999,
                "ack_message_id": 7,
            },
        )
        fake_delay.assert_called_once_with(
            telegram_id=42,
            username="hrach",
            telegram_file_id="file-xyz",
            chat_id=999,
            ack_message_id=7,
        )

    async def test_ack_message_id_is_optional(self, client: AsyncClient, fake_delay):
        response = await client.post(
            "/api/tasks/voice",
            json={
                "telegram_id": 1,
                "telegram_file_id": "f1",
                "chat_id": 1,
            },
        )
        assert response.status_code == 202
        fake_delay.assert_called_once_with(
            telegram_id=1,
            username=None,
            telegram_file_id="f1",
            chat_id=1,
            ack_message_id=None,
        )

    async def test_missing_telegram_file_id_returns_422(self, client: AsyncClient, fake_delay):
        response = await client.post(
            "/api/tasks/voice", json={"telegram_id": 1, "chat_id": 1}
        )
        assert response.status_code == 422
        fake_delay.assert_not_called()

    async def test_missing_chat_id_returns_422(self, client: AsyncClient, fake_delay):
        response = await client.post(
            "/api/tasks/voice", json={"telegram_id": 1, "telegram_file_id": "f1"}
        )
        assert response.status_code == 422

    async def test_broker_unavailable_returns_503(self, client: AsyncClient, fake_delay):
        fake_delay.side_effect = OperationalError("redis is down")

        response = await client.post(
            "/api/tasks/voice",
            json={"telegram_id": 1, "telegram_file_id": "f1", "chat_id": 1},
        )

        assert response.status_code == 503
