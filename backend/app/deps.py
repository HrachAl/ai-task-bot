from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

DbSession = AsyncGenerator[AsyncSession, None]
