import logging

from celery import Task as CeleryTask

from app.db_sync import SyncSessionLocal
from app.exceptions import (
    AudioDownloadError,
    EmptyTranscriptionError,
    InvalidAudioError,
    TelegramAPIError,
    TranscriptionError,
)
from app.integrations.telegram import get_telegram_client
from app.integrations.transcriber import get_transcriber
from app.services.voice import process_voice_message
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

FAILURE_MESSAGES: dict[type[Exception], str] = {
    AudioDownloadError: "⚠️ Couldn't download your voice message. Please try sending it again.",
    InvalidAudioError: "⚠️ That voice message looks empty or unsupported. Please try again.",
    TranscriptionError: (
        "⚠️ Couldn't transcribe your voice message right now. Please try again shortly."
    ),
    EmptyTranscriptionError: (
        "⚠️ Couldn't hear anything in that recording. Please try again and speak clearly."
    ),
}
DEFAULT_FAILURE_MESSAGE = "⚠️ Something went wrong processing your voice message. Please try again."


@celery_app.task(
    name="notify_telegram",
    autoretry_for=(TelegramAPIError,),
    retry_backoff=2,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
)
def notify_telegram_task(
    chat_id: int,
    message: str,
    message_id: int | None = None,
    reply_markup: dict | None = None,
) -> None:
    """Deliver one Telegram notification as its own retryable, queued job —
    decoupled from whatever produced it (transcription success or failure),
    so a transient Telegram/network error is retried here instead of being
    silently dropped by the caller."""
    client = get_telegram_client()
    try:
        if message_id is not None:
            client.edit_message_text(chat_id, message_id, message, reply_markup=reply_markup)
        else:
            client.send_message(chat_id, message, reply_markup=reply_markup)
    except TelegramAPIError:
        client.send_message(chat_id, message, reply_markup=reply_markup)


class VoiceTask(CeleryTask):
    """Notifies the user exactly once, at the point Celery gives up on the
    job — either the exception isn't retryable, or retries are exhausted.
    Individual retry attempts stay silent so the user isn't spammed."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        chat_id = kwargs.get("chat_id")
        ack_message_id = kwargs.get("ack_message_id")
        if chat_id is None:
            logger.error("Voice task %s failed with no chat_id to notify: %r", task_id, exc)
            return

        message = FAILURE_MESSAGES.get(type(exc), DEFAULT_FAILURE_MESSAGE)
        try:
            notify_telegram_task.delay(chat_id, message, message_id=ack_message_id)
        except Exception:
            logger.exception("Failed to enqueue failure notification for chat %s", chat_id)


@celery_app.task(
    bind=True,
    base=VoiceTask,
    name="transcribe_voice",
    autoretry_for=(AudioDownloadError, TranscriptionError),
    retry_backoff=2,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
)
def transcribe_voice_task(
    self: CeleryTask,
    *,
    telegram_id: int,
    username: str | None,
    telegram_file_id: str,
    chat_id: int,
    ack_message_id: int | None = None,
) -> int:
    db = SyncSessionLocal()
    try:
        task = process_voice_message(
            db,
            get_telegram_client(),
            get_transcriber(),
            telegram_id=telegram_id,
            username=username,
            telegram_file_id=telegram_file_id,
            chat_id=chat_id,
            ack_message_id=ack_message_id,
        )
        return task.id
    finally:
        db.close()
