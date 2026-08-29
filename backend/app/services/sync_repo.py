"""Synchronous counterparts of app.services.{users,tasks}, used only by the
Celery worker — Celery tasks run in plain sync code, so they cannot share the
FastAPI app's async engine/session.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Task, TaskStatus, User


def get_or_create_user_sync(db: Session, *, telegram_id: int, username: str | None = None) -> User:
    user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
    if user is not None:
        if username is not None and user.username != username:
            user.username = username
        return user

    # Two concurrent worker jobs for the same new telegram_id (e.g. two
    # voice messages from the same user transcribing at once, with -c 2)
    # can both pass the SELECT above before either commits. Insert inside a
    # SAVEPOINT so a unique-constraint loss only undoes this insert, then
    # re-read the row the other job just created.
    try:
        with db.begin_nested():
            user = User(telegram_id=telegram_id, username=username)
            db.add(user)
            db.flush()
    except IntegrityError:
        user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if user is None:
            raise
    return user


def create_task_sync(
    db: Session,
    *,
    telegram_id: int,
    username: str | None,
    title: str,
    status: TaskStatus = TaskStatus.PENDING,
) -> Task:
    user = get_or_create_user_sync(db, telegram_id=telegram_id, username=username)
    task = Task(user_id=user.id, title=title, status=status)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
