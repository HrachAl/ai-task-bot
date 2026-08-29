import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/tasks")
async def tasks_websocket(websocket: WebSocket) -> None:
    """Realtime sync channel only: on connect, clients are expected to have
    already loaded the full task list via GET /api/tasks. This socket just
    streams task_created / task_updated events as they happen."""
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect clients to send anything; this just blocks
            # until the connection closes, so we notice disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Unexpected error on a /ws/tasks connection")
    finally:
        manager.disconnect(websocket)
