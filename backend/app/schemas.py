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
    """The authenticated user, as returned by GET /api/me.

    Includes ``access_token`` because the caller already proved they hold
    it — the bot uses this endpoint to build the user's personal dashboard
    link, and the dashboard uses it to confirm the token is still valid.
    """

    access_token: str
    dashboard_url: str


class TaskCreate(BaseModel):
    """Payload for creating a task.

    The owner is never taken from the body — it is resolved from the
    caller's credentials (a dashboard bearer token, or the bot acting on
    behalf of a Telegram user), so one user can't create tasks on another
    user's board.
    """

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
    to Celery/Redis without blocking the Telegram handler. The owning user
    comes from the caller's credentials, not from this payload.
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
