import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.handlers import router
from app.bot.middleware import ErrorHandlingMiddleware
from app.core.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


async def main() -> None:
    # No default parse_mode: messages echo user-supplied / transcribed text
    # verbatim, and HTML/Markdown parsing would reject unescaped "<", "&", etc.
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    dp.message.middleware(ErrorHandlingMiddleware())
    dp.callback_query.middleware(ErrorHandlingMiddleware())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
