import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.api_client import BackendError, get_backend_client
from app.bot.validation import ValidationError, validate_text_message, validate_voice_message
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = Router(name="taskbot")

# Status labels shown on the inline keyboard, in the same left-to-right order
# as the Kanban board columns.
STATUS_LABELS = {
    "pending": "⏳ Pending",
    "in_progress": "🔧 In Progress",
    "completed": "✅ Completed",
}


def _status_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label, callback_data=f"status:{task_id}:{value}")
                for value, label in STATUS_LABELS.items()
            ]
        ]
    )


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "👋 Hi! Send me a text message or a voice note and I'll add it as a task.\n"
        "Use /help to see what I can do."
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    settings = get_settings()
    await message.answer(
        "📋 I turn your messages into tasks.\n\n"
        "• Send plain text — it becomes a task right away.\n"
        "• Send a voice note — I'll transcribe it and add it as a task.\n\n"
        f"Voice notes must be under {settings.max_voice_duration_seconds // 60} minute(s) "
        f"and {settings.max_voice_file_mb} MB."
    )


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
    settings = get_settings()
    voice = message.voice

    try:
        validate_voice_message(
            duration=voice.duration,
            file_size=voice.file_size,
            max_duration_seconds=settings.max_voice_duration_seconds,
            max_file_bytes=settings.max_voice_file_bytes,
        )
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    # Ack immediately so the handler never blocks on transcription — the
    # actual work happens asynchronously via Redis/Celery.
    ack = await message.answer("🎤 Got it — transcribing your voice message...")

    try:
        await get_backend_client().enqueue_voice_task(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            telegram_file_id=voice.file_id,
            chat_id=message.chat.id,
            ack_message_id=ack.message_id,
        )
    except BackendError:
        logger.exception(
            "Failed to enqueue voice task for telegram_id=%s", message.from_user.id
        )
        await ack.edit_text(
            "⚠️ Sorry, I couldn't start processing your voice message. Please try again."
        )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    try:
        title = validate_text_message(message.text)
    except ValidationError as exc:
        await message.answer(f"⚠️ {exc}")
        return

    try:
        task = await get_backend_client().create_text_task(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            title=title,
        )
    except BackendError:
        logger.exception(
            "Failed to create text task for telegram_id=%s", message.from_user.id
        )
        await message.answer("⚠️ Sorry, something went wrong saving your task. Please try again.")
        return

    await message.answer(
        f'✅ Task added: "{title}"\nSet a status?',
        reply_markup=_status_keyboard(task["id"]),
    )


@router.callback_query(F.data.startswith("status:"))
async def handle_status_choice(callback: CallbackQuery) -> None:
    _, task_id_raw, status_value = callback.data.split(":", 2)

    try:
        await get_backend_client().update_task_status(
            task_id=int(task_id_raw), status=status_value
        )
    except BackendError:
        logger.exception("Failed to update status for task_id=%s", task_id_raw)
        await callback.answer("⚠️ Couldn't update the status, try again.", show_alert=True)
        return

    await callback.answer(f"Status set to {STATUS_LABELS[status_value]}")
    await callback.message.edit_text(
        f"{callback.message.text.splitlines()[0]}\nStatus: {STATUS_LABELS[status_value]}"
    )


@router.message()
async def handle_unsupported(message: Message) -> None:
    """Catch-all for anything that isn't text, voice, or a known command —
    photos, stickers, documents, unrecognized commands, etc."""
    await message.answer(
        "🤔 I can only turn text messages or voice notes into tasks. "
        "Send one of those, or use /help."
    )
