"""Core voice-message business logic: download -> transcribe -> persist -> notify.

Kept independent of Celery so it can be unit-tested as a plain function with
fake Telegram/Transcriber implementations, and independent of asyncio since
the Celery worker that calls it runs synchronously.
"""

import logging

from sqlalchemy.orm import Session

from app.exceptions import InvalidAudioError
from app.integrations.telegram import TelegramClient
from app.integrations.transcriber import Transcriber
from app.models import Task
from app.services.events_sync import publish_task_event_sync
from app.services.sync_repo import create_task_sync

logger = logging.getLogger(__name__)

MAX_TASK_TITLE_LENGTH = 500

# Mirrors app.bot.handlers.STATUS_LABELS so the voice confirmation offers the
# same status-choice keyboard as a text-created task. Duplicated rather than
# imported: that module is aiogram-specific (bot process), while this is
# rendered by the worker's plain-HTTP Telegram client as raw JSON.
_STATUS_BUTTONS = [
    ("pending", "⏳ Pending"),
    ("in_progress", "🔧 In Progress"),
    ("completed", "✅ Completed"),
]


def _status_keyboard(task_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": label, "callback_data": f"status:{task_id}:{value}"}
                for value, label in _STATUS_BUTTONS
            ]
        ]
    }


def process_voice_message(
    db: Session,
    telegram_client: TelegramClient,
    transcriber: Transcriber,
    *,
    telegram_id: int,
    username: str | None,
    telegram_file_id: str,
    chat_id: int,
    ack_message_id: int | None = None,
) -> Task:
    """Run the full voice pipeline for one message and return the created Task.

    Raises AudioDownloadError / InvalidAudioError / TranscriptionError /
    EmptyTranscriptionError on failure. No Task is created when it raises —
    PostgreSQL only ever holds successfully transcribed tasks. The caller
    (the Celery task) owns retry policy and user-facing failure messaging.
    """
    file_path = telegram_client.get_file_path(telegram_file_id)
    audio_bytes = telegram_client.download_file(file_path)

    if not audio_bytes:
        raise InvalidAudioError("Downloaded voice file is empty")

    filename = file_path.rsplit("/", 1)[-1] if file_path else "voice.ogg"
    transcript = transcriber.transcribe(audio_bytes, filename=filename)
    title = transcript[:MAX_TASK_TITLE_LENGTH]

    task = create_task_sync(db, telegram_id=telegram_id, username=username, title=title)
    logger.info("Created task %s from voice message for telegram_id=%s", task.id, telegram_id)
    try:
        publish_task_event_sync("task_created", task)
    except Exception:
        # Belt-and-suspenders on top of publish_task_event_sync's own safety
        # net: a task already committed to PostgreSQL must not be undone by
        # a broken realtime layer.
        logger.exception("Realtime event publish failed for task %s (task_created)", task.id)

    # Local import: app.worker.tasks imports process_voice_message at module
    # scope, so importing notify_telegram_task back at module scope here
    # would be circular.
    from app.worker.tasks import notify_telegram_task

    try:
        notify_telegram_task.delay(
            chat_id,
            f'✅ Task added: "{title}"\nSet a status?',
            message_id=ack_message_id,
            reply_markup=_status_keyboard(task.id),
        )
    except Exception:
        logger.exception("Failed to enqueue Telegram notification for task %s", task.id)

    return task
