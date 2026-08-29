"""Sync counterpart of app.services.events, for the Celery worker (voice
flow), which runs plain sync code and cannot use the asyncio Redis client."""

import json
import logging

import redis as redis_sync

from app.core.config import get_settings
from app.models import Task
from app.schemas import TaskRead

logger = logging.getLogger(__name__)

_redis_sync: redis_sync.Redis | None = None


def _get_redis_sync() -> redis_sync.Redis:
    global _redis_sync
    if _redis_sync is None:
        settings = get_settings()
        _redis_sync = redis_sync.from_url(settings.redis_pubsub_url, decode_responses=True)
    return _redis_sync


def publish_task_event_sync(event_type: str, task: Task) -> None:
    """Never raises: a task that was already committed to PostgreSQL must
    not fail the worker job just because the realtime notification failed
    (serialization, Redis unreachable, or anything else)."""
    try:
        settings = get_settings()
        payload = {
            "type": event_type,
            "task": TaskRead.model_validate(task).model_dump(mode="json"),
        }
        _get_redis_sync().publish(settings.task_events_channel, json.dumps(payload))
    except Exception:
        logger.exception("Failed to publish %s event for task %s", event_type, task.id)
