"""Tracks live WebSocket connections and fans a message out to all of them.

Deliberately holds no history/state beyond the live socket set — WebSocket is
a synchronization channel, not storage. PostgreSQL remains the source of
truth; a client that missed events (e.g. was offline) re-syncs by re-fetching
GET /api/tasks, not by replaying anything from here.
"""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Every socket is remembered together with the id of the user it
    belongs to, so a task event can be delivered to that user's open tabs
    only. Boards are private; a broadcast must never cross accounts."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, int | None] = {}

    async def connect(self, websocket: WebSocket, user_id: int | None = None) -> None:
        await websocket.accept()
        self._connections[websocket] = user_id
        logger.info(
            "WebSocket connected for user %s (%d total)", user_id, len(self._connections)
        )

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)
        logger.info("WebSocket disconnected (%d total)", len(self._connections))

    async def broadcast(self, message: str, *, user_id: int | None = None) -> None:
        """Send to the sockets of one user, or — when `user_id` is None — to
        every connected client. A client that fails to receive (already gone,
        network blip) is dropped instead of breaking the broadcast for
        everyone else."""
        dead: list[WebSocket] = []
        for connection, owner_id in list(self._connections.items()):
            if user_id is not None and owner_id != user_id:
                continue
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)

        for connection in dead:
            self._connections.pop(connection, None)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()
