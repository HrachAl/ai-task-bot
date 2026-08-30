import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import TaskNotFoundError
from app.models import Task, TaskStatus, User
from app.schemas import TaskCreate, TaskUpdate
from app.services.events import publish_task_event

logger = logging.getLogger(__name__)


async def _publish_safely(event_type: str, task: Task) -> None:
    """A task that was already committed to PostgreSQL must never be failed
    by a broken realtime layer — belt-and-suspenders on top of
    publish_task_event's own internal safety net."""
    try:
        await publish_task_event(event_type, task)
    except Exception:
        logger.exception("Realtime event publish failed for task %s (%s)", task.id, event_type)


async def list_tasks(
    db: AsyncSession, *, owner: User, status: TaskStatus | None = None
) -> list[Task]:
    """Only ever returns the owner's tasks — every board is private."""
    stmt = (
        select(Task).where(Task.user_id == owner.id).order_by(Task.created_at.desc())
    )
    if status is not None:
        stmt = stmt.where(Task.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task(db: AsyncSession, task_id: int, *, owner: User) -> Task:
    """A task owned by someone else is reported as *not found*, not as
    forbidden — otherwise the 403/404 difference would leak which task ids
    exist on other people's boards."""
    task = await db.get(Task, task_id)
    if task is None or task.user_id != owner.id:
        raise TaskNotFoundError(task_id)
    return task


async def create_task(db: AsyncSession, payload: TaskCreate, *, owner: User) -> Task:
    task = Task(
        user_id=owner.id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await _publish_safely("task_created", task)
    return task


async def update_task(
    db: AsyncSession, task_id: int, payload: TaskUpdate, *, owner: User
) -> Task:
    task = await get_task(db, task_id, owner=owner)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    await _publish_safely("task_updated", task)
    return task


async def delete_task(db: AsyncSession, task_id: int, *, owner: User) -> None:
    task = await get_task(db, task_id, owner=owner)
    await db.delete(task)
    await db.commit()
