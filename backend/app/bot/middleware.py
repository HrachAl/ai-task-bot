import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseMiddleware):
    """Catches anything a handler didn't handle itself, so one bad update
    can't crash the polling loop, and gives the user a friendly reply."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logger.exception("Unhandled error while processing update: %r", event)
            try:
                if isinstance(event, Message):
                    await event.answer(
                        "⚠️ Something went wrong on my end. Please try again in a moment."
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "⚠️ Something went wrong on my end.", show_alert=True
                    )
            except Exception:
                logger.exception("Failed to notify user about handler error")
