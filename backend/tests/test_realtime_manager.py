from app.realtime.manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, *, fail_on_send: bool = False):
        self.accepted = False
        self.sent: list[str] = []
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, message: str) -> None:
        if self.fail_on_send:
            raise RuntimeError("connection closed")
        self.sent.append(message)


class TestConnectionManagerConnect:
    async def test_connect_accepts_and_tracks_the_socket(self):
        manager = ConnectionManager()
        ws = FakeWebSocket()

        await manager.connect(ws)

        assert ws.accepted is True
        assert manager.connection_count == 1

    async def test_disconnect_removes_the_socket(self):
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect(ws)

        manager.disconnect(ws)

        assert manager.connection_count == 0

    async def test_disconnect_of_unknown_socket_is_a_no_op(self):
        manager = ConnectionManager()
        manager.disconnect(FakeWebSocket())  # never connected
        assert manager.connection_count == 0


class TestConnectionManagerBroadcast:
    async def test_broadcasts_to_every_connected_client(self):
        manager = ConnectionManager()
        ws1, ws2, ws3 = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
        for ws in (ws1, ws2, ws3):
            await manager.connect(ws)

        await manager.broadcast('{"type": "task_created"}')

        for ws in (ws1, ws2, ws3):
            assert ws.sent == ['{"type": "task_created"}']

    async def test_dead_connection_is_dropped_without_breaking_others(self):
        manager = ConnectionManager()
        alive = FakeWebSocket()
        dead = FakeWebSocket(fail_on_send=True)
        await manager.connect(alive)
        await manager.connect(dead)

        await manager.broadcast("hello")

        assert alive.sent == ["hello"]
        assert manager.connection_count == 1  # dead one was pruned

    async def test_broadcast_with_no_clients_does_not_raise(self):
        manager = ConnectionManager()
        await manager.broadcast("hello")  # should simply be a no-op
