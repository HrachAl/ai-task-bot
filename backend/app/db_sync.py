from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

sync_engine = create_engine(settings.database_url_sync, echo=settings.debug, future=True)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False, autoflush=False)


def get_sync_db() -> Iterator[Session]:
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
