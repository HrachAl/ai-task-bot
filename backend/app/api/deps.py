"""Request authentication.

Two kinds of caller are accepted: the dashboard, with
``Authorization: Bearer <access_token>``, and the bot, a trusted internal
service sending ``X-Internal-Token`` plus the ``X-Telegram-Id`` it acts for.
Both resolve to a ``User``, so no endpoint takes an owner id from the request
body.
"""

import logging

from fastapi import Depends, HTTPException, Query, WebSocket, status
from fastapi.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_db
from app.models import User
from app.services.users import get_or_create_user, get_user_by_access_token

logger = logging.getLogger(__name__)

BEARER_PREFIX = "Bearer "
UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated. Open the dashboard through the link the bot gives you (/dashboard).",
    headers={"WWW-Authenticate": "Bearer"},
)


async def _user_from_bearer(db: AsyncSession, header: str) -> User:
    user = await get_user_by_access_token(db, header[len(BEARER_PREFIX) :].strip())
    if user is None:
        raise UNAUTHENTICATED
    return user


async def _user_from_internal_headers(db: AsyncSession, headers) -> User | None:
    """The bot's path: a shared secret plus the Telegram identity it acts for."""
    settings = get_settings()
    if headers.get("X-Internal-Token") != settings.internal_api_token:
        return None

    raw_telegram_id = headers.get("X-Telegram-Id")
    if not raw_telegram_id:
        return None
    try:
        telegram_id = int(raw_telegram_id)
    except ValueError:
        raise UNAUTHENTICATED from None

    user = await get_or_create_user(
        db, telegram_id=telegram_id, username=headers.get("X-Telegram-Username") or None
    )
    # First contact creates the row and its access token; commit so the token
    # survives even if the request itself later fails.
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith(BEARER_PREFIX):
        return await _user_from_bearer(db, authorization)

    user = await _user_from_internal_headers(db, request.headers)
    if user is not None:
        return user

    raise UNAUTHENTICATED


async def get_ws_user(
    websocket: WebSocket,
    token: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """WebSocket counterpart of `get_current_user`.

    Browsers can't set headers on a handshake, so the token travels as a query
    parameter. Returns None rather than raising — the endpoint closes the
    socket with a status code the client can actually observe.
    """
    return await get_user_by_access_token(db, token)
