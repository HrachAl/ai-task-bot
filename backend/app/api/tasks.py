from fastapi import APIRouter, Depends, HTTPException, Query, status
from kombu.exceptions import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import TaskStatus
from app.schemas import TaskCreate, TaskRead, TaskUpdate, VoiceTaskCreate, VoiceTaskQueued
from app.services import tasks as tasks_service
from app.worker.tasks import transcribe_voice_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[TaskRead]:
    tasks = await tasks_service.list_tasks(db, status=status_filter)
    return tasks


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)) -> TaskRead:
    task = await tasks_service.get_task(db, task_id)
    return task


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)) -> TaskRead:
    task = await tasks_service.create_task(db, payload)
    return task


@router.post("/voice", response_model=VoiceTaskQueued, status_code=status.HTTP_202_ACCEPTED)
async def create_voice_task(payload: VoiceTaskCreate) -> VoiceTaskQueued:
    """Enqueues transcription and returns immediately — no Task row exists
    yet. The Celery worker creates it once it has a transcript."""
    try:
        transcribe_voice_task.delay(
            telegram_id=payload.telegram_id,
            username=payload.username,
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
    task_id: int, payload: TaskUpdate, db: AsyncSession = Depends(get_db)
) -> TaskRead:
    task = await tasks_service.update_task(db, task_id, payload)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await tasks_service.delete_task(db, task_id)
