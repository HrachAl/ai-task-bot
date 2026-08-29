import httpx
import pytest

from app.bot.api_client import BackendClient, BackendError


def make_client(handler) -> BackendClient:
    client = BackendClient(base_url="http://backend-test")
    client._client = httpx.AsyncClient(
        base_url="http://backend-test", transport=httpx.MockTransport(handler)
    )
    return client


class TestCreateTextTask:
    async def test_success_returns_parsed_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/tasks"
            return httpx.Response(201, json={"id": 1, "title": "Buy milk"})

        client = make_client(handler)
        result = await client.create_text_task(telegram_id=1, username="hrach", title="Buy milk")
        assert result == {"id": 1, "title": "Buy milk"}

    async def test_5xx_raises_backend_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "boom"})

        client = make_client(handler)
        with pytest.raises(BackendError):
            await client.create_text_task(telegram_id=1, username=None, title="x")

    async def test_422_raises_backend_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"detail": "invalid"})

        client = make_client(handler)
        with pytest.raises(BackendError):
            await client.create_text_task(telegram_id=1, username=None, title="")

    async def test_network_error_raises_backend_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = make_client(handler)
        with pytest.raises(BackendError):
            await client.create_text_task(telegram_id=1, username=None, title="x")


class TestEnqueueVoiceTask:
    async def test_success_returns_parsed_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/tasks/voice"
            return httpx.Response(202, json={"status": "queued"})

        client = make_client(handler)
        result = await client.enqueue_voice_task(
            telegram_id=1, username=None, telegram_file_id="f1", chat_id=1, ack_message_id=2
        )
        assert result == {"status": "queued"}

    async def test_backend_unreachable_raises_backend_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out")

        client = make_client(handler)
        with pytest.raises(BackendError):
            await client.enqueue_voice_task(
                telegram_id=1, username=None, telegram_file_id="f1", chat_id=1, ack_message_id=None
            )


class TestUpdateTaskStatus:
    async def test_success_returns_parsed_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            assert request.url.path == "/api/tasks/7"
            return httpx.Response(200, json={"id": 7, "status": "completed"})

        client = make_client(handler)
        result = await client.update_task_status(task_id=7, status="completed")
        assert result == {"id": 7, "status": "completed"}

    async def test_error_response_raises_backend_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "not found"})

        client = make_client(handler)
        with pytest.raises(BackendError):
            await client.update_task_status(task_id=999, status="completed")
