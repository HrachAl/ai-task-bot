import asyncio
import os
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db import Base, get_db
from app.main import app

DEFAULT_TEST_TELEGRAM_ID = 1

settings = get_settings()

# The suite always runs against a dedicated `*_test` database so it never touches
# development data. Derived from DATABASE_URL by default; TEST_DATABASE_URL overrides it.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    base_url = settings.database_url
    if base_url.endswith("_test"):
        TEST_DATABASE_URL = base_url
    else:
        db_name = base_url.rsplit("/", 1)[-1]
        TEST_DATABASE_URL = base_url.rsplit("/", 1)[0] + f"/{db_name}_test"

TEST_DATABASE_URL_SYNC = TEST_DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql+psycopg://"
)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create tables once for the session, using its own throwaway event loop
    (kept separate from pytest-asyncio's per-test loops to avoid cross-loop errors)."""

    async def _create() -> None:
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())
    yield

    async def _drop() -> None:
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_drop())


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """One connection + outer transaction per test, rolled back at teardown."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    session = session_factory()

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()
    await engine.dispose()


@pytest.fixture
def sync_db_session() -> Generator[Session, None, None]:
    """Sync counterpart of `db_session`, for testing the Celery worker's
    business logic (app.services.sync_repo / app.services.voice), which runs
    in plain sync code and cannot use the async engine."""
    engine = create_engine(TEST_DATABASE_URL_SYNC, poolclass=NullPool)
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    engine.dispose()


def bot_headers(telegram_id: int, username: str | None = None) -> dict[str, str]:
    """Credentials identical to the ones the real bot sends: the shared
    internal secret plus the Telegram identity it is acting for. Endpoints
    are per-user now, so every request needs to say who it is."""
    headers = {
        "X-Internal-Token": settings.internal_api_token,
        "X-Telegram-Id": str(telegram_id),
    }
    if username:
        headers["X-Telegram-Username"] = username
    return headers


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated as one fixed Telegram user. Tests that need a second
    identity pass `headers=bot_headers(other_id)` on the individual request."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=bot_headers(DEFAULT_TEST_TELEGRAM_ID),
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """No credentials at all — for asserting endpoints actually reject
    unauthenticated callers."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
