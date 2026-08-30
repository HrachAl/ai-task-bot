from fastapi import APIRouter, Depends, HTTPException, Query, status
from kombu.exceptions import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db import get_db
from app.models import TaskStatus, User
from app.schemas import TaskCreate, TaskRead, TaskUpdate, VoiceTaskCreate, VoiceTaskQueued
from app.services import tasks as tasks_service
from app.worker.tasks import transcribe_voice_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskRead]:
    tasks = await tasks_service.list_tasks(db, owner=current_user, status=status_filter)
    return tasks


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    task = await tasks_service.get_task(db, task_id, owner=current_user)
    return task


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    task = await tasks_service.create_task(db, payload, owner=current_user)
    return task


@router.post("/voice", response_model=VoiceTaskQueued, status_code=status.HTTP_202_ACCEPTED)
async def create_voice_task(
    payload: VoiceTaskCreate,
    current_user: User = Depends(get_current_user),
) -> VoiceTaskQueued:
    """Enqueues transcription and returns immediately — no Task row exists
    yet. The Celery worker creates it once it has a transcript, under the
    Telegram identity of the authenticated caller."""
    try:
        transcribe_voice_task.delay(
            telegram_id=current_user.telegram_id,
            username=current_user.username,
            telegram_file_id=payload.telegram_file_id,
            chat_id=payload.chat_id,
            ack_message_id=payload.ack_message_id,
        )
    except OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not queue voice message for processing",
        ) from exc
    return VoiceTaskQueued()


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    task = await tasks_service.update_task(db, task_id, payload, owner=current_user)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await tasks_service.delete_task(db, task_id, owner=current_user)
