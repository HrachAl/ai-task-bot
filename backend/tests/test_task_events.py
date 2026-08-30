from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.models import TaskStatus
from app.services import events as events_module
from app.services import tasks as tasks_service


@pytest.fixture(autouse=True)
def fake_publish(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(tasks_service, "publish_task_event", mock)
    return mock


class TestTaskCreationPublishesEvent:
    async def test_create_task_publishes_task_created(self, client: AsyncClient, fake_publish):
        response = await client.post(
            "/api/tasks", json={"title": "Buy milk"}
        )
        assert response.status_code == 201

        fake_publish.assert_awaited_once()
        event_type, task = fake_publish.await_args.args
        assert event_type == "task_created"
        assert task.title == "Buy milk"


class TestTaskUpdatePublishesEvent:
    async def test_update_task_publishes_task_updated(self, client: AsyncClient, fake_publish):
        create_response = await client.post(
            "/api/tasks", json={"title": "Buy milk"}
        )
        task_id = create_response.json()["id"]
        fake_publish.reset_mock()

        response = await client.patch(f"/api/tasks/{task_id}", json={"status": "completed"})
        assert response.status_code == 200

        fake_publish.assert_awaited_once()
        event_type, task = fake_publish.await_args.args
        assert event_type == "task_updated"
        assert task.status.value == "completed"


class TestTaskDeletionPublishesEvent:
    """Deletion has to be announced too, now that a task can be removed from
    the bot as well as the dashboard — an open board would otherwise keep
    showing a card that no longer exists."""

    async def test_delete_task_publishes_task_deleted(
        self, client: AsyncClient, fake_publish
    ):
        create_response = await client.post("/api/tasks", json={"title": "Temporary"})
        task_id = create_response.json()["id"]
        fake_publish.reset_mock()

        response = await client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 204

        fake_publish.assert_awaited_once()
        event_type, task = fake_publish.await_args.args
        assert event_type == "task_deleted"
        assert task.id == task_id
        assert task.title == "Temporary"

    async def test_the_event_still_names_the_owner_to_route_to(
        self, client: AsyncClient, fake_publish
    ):
        """The payload is read after the row is gone, so it has to be a
        snapshot — including user_id, which is the realtime routing key."""
        created = (await client.post("/api/tasks", json={"title": "Temporary"})).json()
        fake_publish.reset_mock()

        await client.delete(f"/api/tasks/{created['id']}")

        _, task = fake_publish.await_args.args
        assert task.user_id == created["user_id"]


class TestPublishTaskEventNeverRaises:
    """A missed realtime notification must never fail a request that already
    committed to PostgreSQL — task creation must succeed regardless."""

    async def test_create_task_succeeds_even_if_publish_raises(
        self, client: AsyncClient, fake_publish
    ):
        fake_publish.side_effect = RuntimeError("redis exploded")

        response = await client.post(
            "/api/tasks", json={"title": "Should still work"}
        )

        assert response.status_code == 201
        assert response.json()["title"] == "Should still work"

    async def test_publish_task_event_itself_swallows_redis_errors(self, monkeypatch):
        """Exercises the real (unmocked) publish_task_event to confirm its
        own internal safety net, not just the mocked version used above."""

        class ExplodingRedis:
            async def publish(self, *args, **kwargs):
                raise ConnectionError("redis unreachable")

        monkeypatch.setattr(events_module, "_get_redis", lambda: ExplodingRedis())

        now = datetime.now(UTC)
        fake_task = SimpleNamespace(
            id=1,
            user_id=1,
            title="x",
            description=None,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        # Must not raise.
        await events_module.publish_task_event("task_created", fake_task)
