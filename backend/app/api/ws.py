import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import get_ws_user
from app.models import User
from app.realtime.manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

# Close code 4401 ("unauthorized") from the private-use range, mirroring
# HTTP 401 — the browser can read the code and prompt for a fresh link.
WS_UNAUTHORIZED = 4401


@router.websocket("/ws/tasks")
async def tasks_websocket(
    websocket: WebSocket, user: User | None = Depends(get_ws_user)
) -> None:
    """Realtime sync channel only: on connect, clients are expected to have
    already loaded the full task list via GET /api/tasks. This socket just
    streams that user's own task_created / task_updated events as they
    happen — a socket only ever receives events for the account whose token
    opened it."""
    if user is None:
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    await manager.connect(websocket, user_id=user.id)
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
