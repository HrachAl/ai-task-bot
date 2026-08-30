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


class MeRead(UserRead):
    """The authenticated user. Includes ``access_token`` because the caller
    already proved they hold it, and the bot needs it to build the link."""

    access_token: str
    dashboard_url: str


class TaskCreate(BaseModel):
    """Payload for creating a task. The owner is resolved from the caller's
    credentials, never from the body."""

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

    No Task row exists yet: the worker creates one once it has a transcript.
    This only hands the file reference to Celery without blocking the
    Telegram handler.
    """

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
