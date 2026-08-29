import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import TaskNotFoundError
from app.models import Task, TaskStatus
from app.schemas import TaskCreate, TaskUpdate
from app.services.events import publish_task_event
from app.services.users import get_or_create_user

logger = logging.getLogger(__name__)


async def _publish_safely(event_type: str, task: Task) -> None:
    """A task that was already committed to PostgreSQL must never be failed
    by a broken realtime layer — belt-and-suspenders on top of
    publish_task_event's own internal safety net."""
    try:
        await publish_task_event(event_type, task)
    except Exception:
        logger.exception("Realtime event publish failed for task %s (%s)", task.id, event_type)


async def list_tasks(db: AsyncSession, *, status: TaskStatus | None = None) -> list[Task]:
    stmt = select(Task).order_by(Task.created_at.desc())
    if status is not None:
        stmt = stmt.where(Task.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    return task


async def create_task(db: AsyncSession, payload: TaskCreate) -> Task:
    user = await get_or_create_user(
        db, telegram_id=payload.telegram_id, username=payload.username
    )
    task = Task(
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await _publish_safely("task_created", task)
    return task


async def update_task(db: AsyncSession, task_id: int, payload: TaskUpdate) -> Task:
    task = await get_task(db, task_id)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    await _publish_safely("task_updated", task)
    return task


async def delete_task(db: AsyncSession, task_id: int) -> None:
    task = await get_task(db, task_id)
    await db.delete(task)
    await db.commit()
