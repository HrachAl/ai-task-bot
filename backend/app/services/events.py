"""Publishes task lifecycle events for WebSocket clients to consume.

Used by the async request path (FastAPI: text-message task creation, status
updates via PATCH). Publish failures are logged and swallowed — a missed
realtime notification must never fail the request that already committed to
PostgreSQL, which remains the source of truth.
"""

import json
import logging

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.models import Task
from app.schemas import TaskRead

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(settings.redis_pubsub_url, decode_responses=True)
    return _redis


async def publish_task_event(event_type: str, task: Task | TaskRead) -> None:
    """Never raises: a task that was already committed to PostgreSQL must
    not fail the request just because the realtime notification failed
    (serialization, Redis unreachable, or anything else)."""
    try:
        settings = get_settings()
        payload = {
            "type": event_type,
            "task": TaskRead.model_validate(task).model_dump(mode="json"),
        }
        await _get_redis().publish(settings.task_events_channel, json.dumps(payload))
    except Exception:
        logger.exception("Failed to publish %s event for task %s", event_type, task.id)
