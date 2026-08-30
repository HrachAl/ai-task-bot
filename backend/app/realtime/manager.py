"""Tracks live WebSocket connections and fans messages out to them.

Holds no history beyond the live socket set: WebSocket is a synchronization
channel, not storage. A client that missed events re-syncs through
GET /api/tasks.
"""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Each socket is stored with the id of the user it belongs to, so an
    event reaches that user's tabs only. Boards are private."""

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
        """Send to one user's sockets, or to every client when `user_id` is
        None. A socket that fails to receive is dropped rather than breaking
        the broadcast for everyone else."""
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
