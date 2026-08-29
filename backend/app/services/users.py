from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_or_create_user(
    db: AsyncSession, *, telegram_id: int, username: str | None = None
) -> User:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is not None:
        if username is not None and user.username != username:
            user.username = username
        return user

    # Two concurrent requests for the same new telegram_id (e.g. two rapid
    # dashboard submissions, which all share the reserved dashboard user id)
    # can both pass the SELECT above before either commits. Insert inside a
    # SAVEPOINT so a unique-constraint loss only undoes this insert, then
    # re-read the row the other request just created.
    try:
        async with db.begin_nested():
            user = User(telegram_id=telegram_id, username=username)
            db.add(user)
            await db.flush()
    except IntegrityError:
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise
    return user
