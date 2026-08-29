"""Integration tests for /ws/tasks against a real Redis instance (the same
dev Redis used for Celery/pub-sub in this environment) — these exercise the
whole realtime path: publish -> Redis -> listener -> ConnectionManager ->
socket, not just the pieces in isolation.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.models import TaskStatus
from app.realtime.listener import subscribed_event
from app.services.events_sync import publish_task_event_sync


def make_task(**overrides) -> SimpleNamespace:
    now = datetime.now(UTC)
    defaults = dict(
        id=1, user_id=1, title="Buy milk", description=None,
        status=TaskStatus.PENDING, created_at=now, updated_at=now,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestWebSocketConnection:
    def test_connect_and_receive_a_broadcast_event(self):
        with TestClient(app) as test_client:
            assert subscribed_event.wait(timeout=2), "listener never subscribed"
            with test_client.websocket_connect("/ws/tasks") as websocket:
                task = make_task(id=101, title="Realtime task")
                publish_task_event_sync("task_created", task)

                message = websocket.receive_json()

        assert message["type"] == "task_created"
        assert message["task"]["id"] == 101
        assert message["task"]["title"] == "Realtime task"

    def test_multiple_clients_all_receive_the_same_event(self):
        with TestClient(app) as test_client:
            assert subscribed_event.wait(timeout=2), "listener never subscribed"
            with test_client.websocket_connect("/ws/tasks") as ws1, \
                 test_client.websocket_connect("/ws/tasks") as ws2:
                task = make_task(id=202, title="Shared task")
                publish_task_event_sync("task_updated", task)

                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()

        assert msg1 == msg2
        assert msg1["type"] == "task_updated"

    def test_one_client_disconnecting_does_not_affect_the_other(self):
        with TestClient(app) as test_client:
            assert subscribed_event.wait(timeout=2), "listener never subscribed"
            with test_client.websocket_connect("/ws/tasks") as ws1:
                with test_client.websocket_connect("/ws/tasks") as ws2:
                    pass  # ws2 disconnects here

                task = make_task(id=303, title="Still works")
                publish_task_event_sync("task_created", task)

                message = ws1.receive_json()

        assert message["task"]["id"] == 303
