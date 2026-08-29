from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "taskbot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Explicitly imported so `celery -A app.worker.celery_app worker` registers
    # the task even though nothing else in this module touches app.worker.tasks.
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_time_limit=180,
    task_soft_time_limit=150,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue="transcription",
    timezone="UTC",
)
