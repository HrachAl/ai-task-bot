"""Bridges Redis pub/sub to the in-process ConnectionManager.

Both the FastAPI request handlers (text flow) and the separate Celery worker
process (voice flow) publish task events to this Redis channel. Only the
FastAPI process holds live WebSocket connections, so this listener is what
lets a worker in a different process update the browser: it runs once per
FastAPI process, subscribes for the process's lifetime, and re-broadcasts
whatever it receives to every connected client.
"""

import asyncio
import json
import logging
import threading

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.realtime.manager import manager

logger = logging.getLogger(__name__)

# Set once the Redis SUBSCRIBE has actually registered server-side. PUBLISH
# has no delivery guarantee to a subscriber that hasn't finished subscribing
# yet, so tests wait on this instead of racing a publish against startup.
subscribed_event = threading.Event()


NO_RECIPIENT = -1
"""Routing key that matches no user (real ids are positive). An event whose
owner we can't determine is delivered to nobody rather than to everybody:
the affected dashboard re-syncs on its next refresh, which is a far better
failure mode than leaking one account's task into another's tab."""


def _owner_of(raw: str) -> int:
    """Which user's board does this event belong to?

    Every payload we publish carries the task's `user_id` — it is the routing
    key that keeps one account's events out of another account's tabs.
    """
    try:
        return int(json.loads(raw)["task"]["user_id"])
    except (ValueError, TypeError, KeyError):
        logger.warning("Realtime event without a resolvable user_id — not routed")
        return NO_RECIPIENT


async def redis_listener() -> None:
    subscribed_event.clear()
    settings = get_settings()
    redis_client = aioredis.from_url(settings.redis_pubsub_url, decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(settings.task_events_channel)
    subscribed_event.set()
    logger.info(
        "Subscribed to Redis channel '%s' for realtime task events",
        settings.task_events_channel,
    )

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await manager.broadcast(message["data"], user_id=_owner_of(message["data"]))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Redis listener crashed")
        raise
    finally:
        subscribed_event.clear()
        await pubsub.unsubscribe(settings.task_events_channel)
        await pubsub.aclose()
        await redis_client.aclose()
