import httpx
import pytest

from app.bot.api_client import BackendClient, BackendError


def make_client(handler) -> BackendClient:
    client = BackendClient(base_url="http://backend-test", internal_token="secret")
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
        result = await client.update_task_status(
            telegram_id=1, username=None, task_id=7, status="completed"
        )
        assert result == {"id": 7, "status": "completed"}

    async def test_error_response_raises_backend_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "not found"})

        client = make_client(handler)
        with pytest.raises(BackendError):
            await client.update_task_status(
                telegram_id=1, username=None, task_id=999, status="completed"
            )


class TestActingOnBehalfOfAUser:
    """The bot has no personal token of its own: it proves it is the trusted
    internal service and names the Telegram user it is acting for. Every call
    must carry that, or the backend has no way to pick the right board."""

    async def test_every_request_carries_the_internal_credentials(self):
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, json=[])

        client = make_client(handler)
        await client.list_tasks(telegram_id=555, username="hrach")

        assert seen["x-internal-token"] == "secret"
        assert seen["x-telegram-id"] == "555"
        assert seen["x-telegram-username"] == "hrach"

    async def test_username_header_is_omitted_when_unknown(self):
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, json=[])

        client = make_client(handler)
        await client.list_tasks(telegram_id=555, username=None)

        assert "x-telegram-username" not in seen


class TestListAndGetTasks:
    async def test_list_tasks_returns_the_parsed_list(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/api/tasks"
            return httpx.Response(200, json=[{"id": 1, "title": "Buy milk"}])

        client = make_client(handler)
        assert await client.list_tasks(telegram_id=1, username=None) == [
            {"id": 1, "title": "Buy milk"}
        ]

    async def test_get_task_requests_the_right_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/tasks/12"
            return httpx.Response(200, json={"id": 12})

        client = make_client(handler)
        assert await client.get_task(telegram_id=1, username=None, task_id=12) == {"id": 12}

    async def test_get_task_error_raises_backend_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "Task 12 not found"})

        client = make_client(handler)
        with pytest.raises(BackendError):
            await client.get_task(telegram_id=1, username=None, task_id=12)


class TestGetMe:
    async def test_returns_the_dashboard_url(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/me"
            return httpx.Response(200, json={"dashboard_url": "http://board/?token=abc"})

        client = make_client(handler)
        result = await client.get_me(telegram_id=1, username=None)
        assert result["dashboard_url"] == "http://board/?token=abc"


class TestDeleteTask:
    async def test_a_204_with_no_body_is_not_treated_as_an_error(self):
        """DELETE answers 204 with an empty body — parsing it as JSON would
        blow up on an otherwise successful delete."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            assert request.url.path == "/api/tasks/9"
            return httpx.Response(204)

        client = make_client(handler)
        assert await client.delete_task(telegram_id=1, username=None, task_id=9) is None

    async def test_deleting_someone_elses_task_raises_backend_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"detail": "Task 9 not found"})

        client = make_client(handler)
        with pytest.raises(BackendError):
            await client.delete_task(telegram_id=1, username=None, task_id=9)
