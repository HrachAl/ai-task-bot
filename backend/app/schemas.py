from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import TaskStatus


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    created_at: datetime
    updated_at: datetime


DASHBOARD_TELEGRAM_ID = 0
"""Sentinel telegram_id for tasks created from the web dashboard, which has
no Telegram identity of its own. Reserved — real Telegram user ids are always
positive, so this can never collide with an actual bot user."""


class TaskCreate(BaseModel):
    """Payload for creating a task.

    ``telegram_id`` identifies (and lazily creates) the owning user. There is
    no auth layer yet, so the caller is trusted to supply the correct
    identity — this is how the Telegram bot calls this endpoint. It's
    optional because the web dashboard has no Telegram identity and simply
    omits it, falling back to a reserved dashboard user.
    """

    telegram_id: int = DASHBOARD_TELEGRAM_ID
    username: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus = TaskStatus.PENDING

    @model_validator(mode="after")
    def strip_title(self) -> "TaskCreate":
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("title must not be blank")
        return self


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "TaskUpdate":
        if self.title is None and self.description is None and self.status is None:
            raise ValueError("at least one field (title, description, status) must be provided")
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("title must not be blank")
        return self


class VoiceTaskCreate(BaseModel):
    """Payload the bot sends to enqueue a voice message for transcription.

    No Task row is created yet at this point — only once the worker has a
    transcript. This endpoint's only job is to hand the file reference off
    to Celery/Redis without blocking the Telegram handler.
    """

    telegram_id: int
    username: str | None = Field(default=None, max_length=64)
    telegram_file_id: str = Field(min_length=1)
    chat_id: int
    ack_message_id: int | None = None


class VoiceTaskQueued(BaseModel):
    status: str = "queued"


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: str | None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
