import logging
from datetime import datetime

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

# How many tasks /list shows. Telegram caps how big an inline keyboard can
# usefully get, and a longer list stops being scannable on a phone anyway —
# the dashboard is the right place for the full board.
LIST_LIMIT = 20
BUTTON_TITLE_LIMIT = 32


def _actor(event: Message | CallbackQuery) -> dict:
    """Who this update is from, in the shape the backend client expects.

    Telegram identity is the only identity in this project — there is no
    login — so every backend call carries it.
    """
    return {"telegram_id": event.from_user.id, "username": event.from_user.username}


def _status_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label, callback_data=f"status:{task_id}:{value}")
                for value, label in STATUS_LABELS.items()
            ]
        ]
    )


def _shorten(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def _format_created_at(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        return datetime.fromisoformat(raw).strftime("%d %b %Y, %H:%M")
    except ValueError:
        return raw


def _task_view(task: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Render one opened task: its details plus the buttons that change its
    status. This is the same view whether it was reached from /list or from
    the confirmation message right after creation, so changing a status
    always looks and behaves the same way."""
    status = task.get("status", "pending")
    lines = [f"📌 {task['title']}"]
    if task.get("description"):
        lines.append("")
        lines.append(task["description"])
    lines += [
        "",
        f"Status: {STATUS_LABELS.get(status, status)}",
        f"Created: {_format_created_at(task.get('created_at'))}",
        f"Task #{task['id']}",
    ]

    # The current status is marked rather than hidden, so the row of buttons
    # doubles as an indicator of where the task stands.
    status_row = [
        InlineKeyboardButton(
            text=("• " + label) if value == status else label,
            callback_data=f"status:{task['id']}:{value}",
        )
        for value, label in STATUS_LABELS.items()
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            status_row,
            [InlineKeyboardButton(text="⬅️ Back to my tasks", callback_data="list")],
        ]
    )
    return "\n".join(lines), keyboard


def _list_view(tasks: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    shown = tasks[:LIST_LIMIT]
    header = f"📋 Your tasks ({len(tasks)})"
    if len(tasks) > len(shown):
        header += f" — showing the {len(shown)} most recent"
    header += "\n\nTap a task to open it and change its status."

    rows = [
        [
            InlineKeyboardButton(
                text=f"{STATUS_LABELS[task['status']].split()[0]} "
                f"{_shorten(task['title'], BUTTON_TITLE_LIMIT)}",
                callback_data=f"open:{task['id']}",
            )
        ]
        for task in shown
    ]
    return header, InlineKeyboardMarkup(inline_keyboard=rows)


async def _render(
    callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> None:
    """Edit the message in place instead of piling up new ones — the bot
    behaves like a small app with screens, not a chat log."""
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        # Telegram rejects an edit that changes nothing (e.g. re-selecting
        # the status a task already has). Nothing is wrong; just move on.
        logger.debug("Message edit skipped (unchanged content)", exc_info=True)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "👋 Hi! Send me a text message or a voice note and I'll add it as a task.\n\n"
        "• /list — see your tasks and change their status\n"
        "• /dashboard — open your personal web board\n"
        "• /help — everything I can do"
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    settings = get_settings()
    await message.answer(
        "📋 I turn your messages into tasks.\n\n"
        "• Send plain text — it becomes a task right away.\n"
        "• Send a voice note — I'll transcribe it and add it as a task.\n"
        "• /list — browse your tasks; tap one to open it and change its status.\n"
        "• /dashboard — a private link to your own Kanban board in the browser.\n\n"
        f"Voice notes must be under {settings.max_voice_duration_seconds // 60} minute(s) "
        f"and {settings.max_voice_file_mb} MB.\n\n"
        "Your tasks are yours alone — nobody else's bot chat or board can see them."
    )


@router.message(Command("dashboard"))
async def handle_dashboard(message: Message) -> None:
    """Hand the user a link that logs them straight into their own board.

    This is the whole 'registration' flow: the link carries a personal token
    tied to this Telegram account, so there is no sign-up form and no
    password, but every person still gets a separate dashboard.
    """
    try:
        me = await get_backend_client().get_me(**_actor(message))
    except BackendError:
        logger.exception("Failed to fetch dashboard link for telegram_id=%s", message.from_user.id)
        await message.answer("⚠️ Couldn't get your dashboard link right now. Try again shortly.")
        return

    await message.answer(
        "🔐 Here is your private dashboard link:\n"
        f"{me['dashboard_url']}\n\n"
        "It signs you in automatically and only shows your own tasks. "
        "Keep it to yourself — anyone with this link can see your board.",
        disable_web_page_preview=True,
    )


@router.message(Command("list"))
async def handle_list(message: Message) -> None:
    try:
        tasks = await get_backend_client().list_tasks(**_actor(message))
    except BackendError:
        logger.exception("Failed to list tasks for telegram_id=%s", message.from_user.id)
        await message.answer("⚠️ Couldn't load your tasks right now. Please try again.")
        return

    if not tasks:
        await message.answer(
            "📭 You don't have any tasks yet.\n"
            "Send me a text message or a voice note and I'll create the first one."
        )
        return

    text, keyboard = _list_view(tasks)
    await message.answer(text, reply_markup=keyboard)


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
            **_actor(message),
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
        task = await get_backend_client().create_text_task(**_actor(message), title=title)
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


@router.callback_query(F.data.startswith("open:"))
async def handle_open_task(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":", 1)[1])

    try:
        task = await get_backend_client().get_task(**_actor(callback), task_id=task_id)
    except BackendError:
        logger.exception("Failed to open task_id=%s", task_id)
        await callback.answer("⚠️ Couldn't open that task.", show_alert=True)
        return

    await callback.answer()
    await _render(callback, *_task_view(task))


@router.callback_query(F.data == "list")
async def handle_back_to_list(callback: CallbackQuery) -> None:
    try:
        tasks = await get_backend_client().list_tasks(**_actor(callback))
    except BackendError:
        logger.exception("Failed to list tasks for telegram_id=%s", callback.from_user.id)
        await callback.answer("⚠️ Couldn't load your tasks.", show_alert=True)
        return

    await callback.answer()
    if not tasks:
        await _render(callback, "📭 You don't have any tasks yet.")
        return
    await _render(callback, *_list_view(tasks))


@router.callback_query(F.data.startswith("status:"))
async def handle_status_choice(callback: CallbackQuery) -> None:
    _, task_id_raw, status_value = callback.data.split(":", 2)

    try:
        task = await get_backend_client().update_task_status(
            **_actor(callback), task_id=int(task_id_raw), status=status_value
        )
    except BackendError:
        logger.exception("Failed to update status for task_id=%s", task_id_raw)
        await callback.answer("⚠️ Couldn't update the status, try again.", show_alert=True)
        return

    await callback.answer(f"Status set to {STATUS_LABELS[status_value]}")
    # Redraw as the full task view: after a change from the creation
    # confirmation the message becomes an openable task like any other, and
    # after a change from /list it simply refreshes in place.
    await _render(callback, *_task_view(task))


@router.message()
async def handle_unsupported(message: Message) -> None:
    """Catch-all for anything that isn't text, voice, or a known command —
    photos, stickers, documents, unrecognized commands, etc."""
    await message.answer(
        "🤔 I can only turn text messages or voice notes into tasks. "
        "Send one of those, or use /help."
    )
