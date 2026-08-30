"""Concurrency tests for get_or_create_user (async + sync). These need real
independent connections racing against each other, so unlike the rest of the
suite they don't use the single-shared-transaction `db_session` fixture —
that pattern is for isolation/speed, not for reproducing a genuine race.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.services.sync_repo import get_or_create_user_sync
from app.services.users import get_or_create_user
from tests.conftest import TEST_DATABASE_URL, TEST_DATABASE_URL_SYNC


class TestConcurrentUserCreationAsync:
    async def test_concurrent_requests_for_a_new_telegram_id_resolve_to_one_user(self):
        engine = create_async_engine(TEST_DATABASE_URL)
        telegram_id = 900_000_001

        async def create_one() -> int:
            async with engine.connect() as conn, conn.begin():
                session = AsyncSession(bind=conn, expire_on_commit=False)
                user = await get_or_create_user(session, telegram_id=telegram_id)
                await session.flush()
                return user.id

        try:
            results = await asyncio.gather(*[create_one() for _ in range(5)])
            assert len(set(results)) == 1, f"expected one user id, got {results}"
        finally:
            async with engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM users WHERE telegram_id = :tid"), {"tid": telegram_id}
                )
            await engine.dispose()


class TestConcurrentUserCreationSync:
    def test_concurrent_worker_jobs_for_a_new_telegram_id_resolve_to_one_user(self):
        telegram_id = 900_000_002
        # A session factory of this test's own, pointed at the test database
        # — the worker's global SyncSessionLocal is bound to the app's real
        # DATABASE_URL, which the suite must never write to.
        engine = create_engine(TEST_DATABASE_URL_SYNC)
        session_factory = sessionmaker(bind=engine)

        def create_one() -> int:
            with session_factory() as db:
                user = get_or_create_user_sync(db, telegram_id=telegram_id)
                db.commit()
                return user.id

        try:
            with ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(lambda _: create_one(), range(5)))
            assert len(set(results)) == 1, f"expected one user id, got {results}"
        finally:
            with session_factory() as db:
                db.execute(text("DELETE FROM users WHERE telegram_id = :tid"), {"tid": telegram_id})
                db.commit()
            engine.dispose()
