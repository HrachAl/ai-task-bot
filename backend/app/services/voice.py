"""Core voice-message business logic: download -> transcribe -> persist -> notify.

Kept independent of Celery so it can be unit-tested as a plain function with
fake Telegram/Transcriber implementations, and independent of asyncio since
the Celery worker that calls it runs synchronously.
"""

import logging
import re

from sqlalchemy.orm import Session

from app.exceptions import InvalidAudioError
from app.integrations.telegram import TelegramClient
from app.integrations.transcriber import Transcriber
from app.models import Task
from app.services.events_sync import publish_task_event_sync
from app.services.sync_repo import create_task_sync

logger = logging.getLogger(__name__)

# A Kanban card needs a headline, not a monologue. Anything past this goes
# into the description, so a long recording stays fully readable without
# turning the board into a wall of text.
MAX_TASK_TITLE_LENGTH = 120
# Matches TaskCreate.description in the API schema, so a voice task can never
# hold something the REST endpoint would reject.
MAX_TASK_DESCRIPTION_LENGTH = 5000

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s")


def split_transcript(transcript: str) -> tuple[str, str | None]:
    """Turn a transcript into (title, description).

    A short note becomes the title alone. A longer one is headlined by its
    first sentence and keeps the full text in the description — nothing the
    user said is thrown away, which is the whole point of raising the
    duration limit.
    """
    full = " ".join(transcript.split())
    if len(full) <= MAX_TASK_TITLE_LENGTH:
        return full, None

    # Prefer a sentence boundary; Whisper punctuates, so this usually gives a
    # natural headline rather than a cut-off phrase.
    first_sentence = _SENTENCE_END.split(full, maxsplit=1)[0]
    if len(first_sentence) <= MAX_TASK_TITLE_LENGTH:
        title = first_sentence
    else:
        # No usable boundary — cut on a word instead of mid-syllable.
        head = full[:MAX_TASK_TITLE_LENGTH - 1]
        cut = head.rsplit(" ", 1)[0] if " " in head else head
        title = cut + "…"

    return title, full[:MAX_TASK_DESCRIPTION_LENGTH]


# Mirrors app.bot.handlers.STATUS_LABELS. Duplicated rather than imported:
# that module is aiogram-specific, while this is rendered by the worker's
# plain-HTTP Telegram client as raw JSON.
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
    title, description = split_transcript(transcript)

    task = create_task_sync(
        db,
        telegram_id=telegram_id,
        username=username,
        title=title,
        description=description,
    )
    logger.info("Created task %s from voice message for telegram_id=%s", task.id, telegram_id)
    try:
        publish_task_event_sync("task_created", task)
    except Exception:
        # A task already committed to PostgreSQL must not be undone by a
        # broken realtime layer.
        logger.exception("Realtime event publish failed for task %s (task_created)", task.id)

    # Local import: app.worker.tasks imports process_voice_message at module
    # scope, so importing it back here would be circular.
    from app.worker.tasks import notify_telegram_task

    saved_in_full = "\n📄 Full transcript saved in the task." if description else ""
    try:
        notify_telegram_task.delay(
            chat_id,
            f'✅ Task added: "{title}"{saved_in_full}\nSet a status?',
            message_id=ack_message_id,
            reply_markup=_status_keyboard(task.id),
        )
    except Exception:
        logger.exception("Failed to enqueue Telegram notification for task %s", task.id)

    return task
