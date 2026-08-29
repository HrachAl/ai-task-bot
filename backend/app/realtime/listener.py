"""Bridges Redis pub/sub to the in-process ConnectionManager.

Both the FastAPI request handlers (text flow) and the separate Celery worker
process (voice flow) publish task events to this Redis channel. Only the
FastAPI process holds live WebSocket connections, so this listener is what
lets a worker in a different process update the browser: it runs once per
FastAPI process, subscribes for the process's lifetime, and re-broadcasts
whatever it receives to every connected client.
"""

import asyncio
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
            await manager.broadcast(message["data"])
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
