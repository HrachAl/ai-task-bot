import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import TaskNotFoundError
from app.models import Task, TaskStatus, User
from app.schemas import TaskCreate, TaskRead, TaskUpdate
from app.services.events import publish_task_event

logger = logging.getLogger(__name__)


async def _publish_safely(event_type: str, task: Task | TaskRead) -> None:
    """A change already committed to PostgreSQL must not be failed by a
    broken realtime layer."""
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
    """A task owned by someone else reads as not found, not forbidden: a 403
    would confirm the id exists on another board."""
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
    # Snapshot first: once the row is gone its attributes can't be read, and
    # the event still has to name the task and the board it left.
    deleted = TaskRead.model_validate(task)
    await db.delete(task)
    await db.commit()
    await _publish_safely("task_deleted", deleted)
