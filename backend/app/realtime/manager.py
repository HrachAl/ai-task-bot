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
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("WebSocket connected (%d total)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        logger.info("WebSocket disconnected (%d total)", len(self._connections))

    async def broadcast(self, message: str) -> None:
        """Sends to every connected client. A client that fails to receive
        (already gone, network blip) is dropped instead of breaking the
        broadcast for everyone else."""
        dead: list[WebSocket] = []
        for connection in list(self._connections):
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)

        for connection in dead:
            self._connections.discard(connection)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()
