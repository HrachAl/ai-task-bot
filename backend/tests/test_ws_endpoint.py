"""Integration tests for /ws/tasks against a real Redis instance (the same
dev Redis used for Celery/pub-sub in this environment) — these exercise the
whole realtime path: publish -> Redis -> listener -> ConnectionManager ->
socket, not just the pieces in isolation.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_ws_user
from app.main import app
from app.models import TaskStatus
from app.realtime.listener import subscribed_event
from app.services.events_sync import publish_task_event_sync

CONNECTING_USER_ID = 1


@pytest.fixture(autouse=True)
def ws_identity():
    """Stands in for the token lookup so these tests stay about the realtime
    path. Mutate `.user_id` to open the next socket as somebody else."""
    holder = SimpleNamespace(user_id=CONNECTING_USER_ID)
    app.dependency_overrides[get_ws_user] = lambda: SimpleNamespace(id=holder.user_id)
    yield holder
    app.dependency_overrides.clear()


def make_task(**overrides) -> SimpleNamespace:
    now = datetime.now(UTC)
    defaults = dict(
        id=1, user_id=CONNECTING_USER_ID, title="Buy milk", description=None,
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


class TestWebSocketIsPerUser:
    def test_a_socket_only_receives_its_own_users_events(self, ws_identity):
        """The realtime channel is scoped the same way the REST API is."""
        with TestClient(app) as test_client:
            assert subscribed_event.wait(timeout=2), "listener never subscribed"
            with test_client.websocket_connect("/ws/tasks") as mine:
                ws_identity.user_id = 999
                with test_client.websocket_connect("/ws/tasks") as theirs:
                    publish_task_event_sync("task_created", make_task(id=404, user_id=999))

                    # Only the second socket is a recipient...
                    assert theirs.receive_json()["task"]["id"] == 404

                    # ...and the first one gets the next event addressed to it,
                    # proving it never saw the one in between.
                    publish_task_event_sync(
                        "task_created", make_task(id=505, user_id=CONNECTING_USER_ID)
                    )
                    assert mine.receive_json()["task"]["id"] == 505

    def test_an_unauthenticated_socket_is_closed(self):
        app.dependency_overrides[get_ws_user] = lambda: None
        with TestClient(app) as test_client:
            with pytest.raises(Exception):
                with test_client.websocket_connect("/ws/tasks") as websocket:
                    websocket.receive_json()
