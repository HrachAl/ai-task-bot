from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.exceptions import (
    AudioDownloadError,
    EmptyTranscriptionError,
    InvalidAudioError,
    TranscriptionError,
)
from app.models import Task
from app.services import voice as voice_module
from app.services.voice import process_voice_message


@pytest.fixture(autouse=True)
def fake_publish_sync(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(voice_module, "publish_task_event_sync", mock)
    return mock


@pytest.fixture(autouse=True)
def fake_notify_delay(monkeypatch):
    from app.worker.tasks import notify_telegram_task

    mock = MagicMock()
    monkeypatch.setattr(notify_telegram_task, "delay", mock)
    return mock


class FakeTelegramClient:
    def __init__(self, *, file_path="voice/file_1.oga", audio=b"fake-audio-bytes", fail_with=None):
        self.file_path = file_path
        self.audio = audio
        self.fail_with = fail_with

    def get_file_path(self, file_id: str) -> str:
        if self.fail_with is not None:
            raise self.fail_with
        return self.file_path

    def download_file(self, file_path: str) -> bytes:
        return self.audio


class FakeTranscriber:
    def __init__(self, *, text: str = "Buy milk", error: Exception | None = None):
        self.text = text
        self.error = error
        self.calls: list[dict] = []

    def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        self.calls.append({"audio_bytes": audio_bytes, "filename": filename})
        if self.error is not None:
            raise self.error
        return self.text


def count_tasks(db) -> int:
    return len(db.execute(select(Task)).scalars().all())


class TestVoicePipelineHappyPath:
    def test_creates_task_with_transcribed_title(self, sync_db_session):
        telegram = FakeTelegramClient()
        transcriber = FakeTranscriber(text="Buy milk")

        task = process_voice_message(
            sync_db_session,
            telegram,
            transcriber,
            telegram_id=100,
            username="hrach",
            telegram_file_id="file-1",
            chat_id=100,
            ack_message_id=42,
        )

        assert task.title == "Buy milk"
        assert task.status.value == "pending"
        assert task.user_id is not None

    def test_publishes_task_created_event(self, sync_db_session, fake_publish_sync):
        telegram = FakeTelegramClient()
        transcriber = FakeTranscriber(text="Buy milk")

        task = process_voice_message(
            sync_db_session, telegram, transcriber,
            telegram_id=100, username="hrach", telegram_file_id="file-1", chat_id=100,
        )

        fake_publish_sync.assert_called_once_with("task_created", task)

    def test_sends_confirmation_editing_the_ack_message(self, sync_db_session, fake_notify_delay):
        telegram = FakeTelegramClient()
        transcriber = FakeTranscriber(text="Write report")

        task = process_voice_message(
            sync_db_session,
            telegram,
            transcriber,
            telegram_id=101,
            username=None,
            telegram_file_id="file-2",
            chat_id=101,
            ack_message_id=7,
        )

        fake_notify_delay.assert_called_once()
        args, kwargs = fake_notify_delay.call_args
        assert args[0] == 101
        assert "Write report" in args[1]
        assert kwargs["message_id"] == 7

    def test_confirmation_offers_the_same_status_keyboard_as_text_tasks(
        self, sync_db_session, fake_notify_delay
    ):
        telegram = FakeTelegramClient()
        transcriber = FakeTranscriber(text="Write report")

        task = process_voice_message(
            sync_db_session, telegram, transcriber,
            telegram_id=102, username=None, telegram_file_id="file-3", chat_id=102,
        )

        _, kwargs = fake_notify_delay.call_args
        buttons = kwargs["reply_markup"]["inline_keyboard"][0]
        callback_data = [button["callback_data"] for button in buttons]
        assert callback_data == [
            f"status:{task.id}:pending",
            f"status:{task.id}:in_progress",
            f"status:{task.id}:completed",
        ]

    def test_reuses_existing_user_across_calls(self, sync_db_session):
        telegram = FakeTelegramClient()
        transcriber = FakeTranscriber(text="First")

        first = process_voice_message(
            sync_db_session, telegram, transcriber,
            telegram_id=202, username="same", telegram_file_id="f1", chat_id=202,
        )
        transcriber2 = FakeTranscriber(text="Second")
        second = process_voice_message(
            sync_db_session, telegram, transcriber2,
            telegram_id=202, username="same", telegram_file_id="f2", chat_id=202,
        )

        assert first.user_id == second.user_id

    def test_transcript_longer_than_limit_is_truncated(self, sync_db_session):
        telegram = FakeTelegramClient()
        long_text = "x" * 600
        transcriber = FakeTranscriber(text=long_text)

        task = process_voice_message(
            sync_db_session, telegram, transcriber,
            telegram_id=303, username=None, telegram_file_id="f1", chat_id=303,
        )

        assert len(task.title) == 500

    def test_passes_filename_derived_from_telegram_file_path(self, sync_db_session):
        telegram = FakeTelegramClient(file_path="voice/AwAC123.oga")
        transcriber = FakeTranscriber(text="hi")

        process_voice_message(
            sync_db_session, telegram, transcriber,
            telegram_id=404, username=None, telegram_file_id="f1", chat_id=404,
        )

        assert transcriber.calls[0]["filename"] == "AwAC123.oga"


class TestVoicePipelineFailures:
    def test_download_failure_raises_and_creates_no_task(self, sync_db_session):
        telegram = FakeTelegramClient(fail_with=AudioDownloadError("boom"))
        transcriber = FakeTranscriber()

        before = count_tasks(sync_db_session)
        with pytest.raises(AudioDownloadError):
            process_voice_message(
                sync_db_session, telegram, transcriber,
                telegram_id=1, username=None, telegram_file_id="f1", chat_id=1,
            )

        assert count_tasks(sync_db_session) == before

    def test_failure_does_not_publish_an_event(
        self, sync_db_session, fake_publish_sync
    ):
        telegram = FakeTelegramClient(fail_with=AudioDownloadError("boom"))
        transcriber = FakeTranscriber()

        with pytest.raises(AudioDownloadError):
            process_voice_message(
                sync_db_session, telegram, transcriber,
                telegram_id=1, username=None, telegram_file_id="f1", chat_id=1,
            )

        fake_publish_sync.assert_not_called()

    def test_empty_audio_raises_invalid_audio_error(self, sync_db_session):
        telegram = FakeTelegramClient(audio=b"")
        transcriber = FakeTranscriber()

        before = count_tasks(sync_db_session)
        with pytest.raises(InvalidAudioError):
            process_voice_message(
                sync_db_session, telegram, transcriber,
                telegram_id=1, username=None, telegram_file_id="f1", chat_id=1,
            )

        assert count_tasks(sync_db_session) == before
        assert transcriber.calls == []  # never reached transcription

    def test_transcription_api_failure_raises_and_creates_no_task(self, sync_db_session):
        telegram = FakeTelegramClient()
        transcriber = FakeTranscriber(error=TranscriptionError("openai down"))

        before = count_tasks(sync_db_session)
        with pytest.raises(TranscriptionError):
            process_voice_message(
                sync_db_session, telegram, transcriber,
                telegram_id=1, username=None, telegram_file_id="f1", chat_id=1,
            )

        assert count_tasks(sync_db_session) == before

    def test_empty_transcription_raises_and_creates_no_task(self, sync_db_session):
        telegram = FakeTelegramClient()
        transcriber = FakeTranscriber(error=EmptyTranscriptionError("silence"))

        before = count_tasks(sync_db_session)
        with pytest.raises(EmptyTranscriptionError):
            process_voice_message(
                sync_db_session, telegram, transcriber,
                telegram_id=1, username=None, telegram_file_id="f1", chat_id=1,
            )

        assert count_tasks(sync_db_session) == before

    def test_failure_does_not_send_a_confirmation(self, sync_db_session, fake_notify_delay):
        telegram = FakeTelegramClient(fail_with=AudioDownloadError("boom"))
        transcriber = FakeTranscriber()

        with pytest.raises(AudioDownloadError):
            process_voice_message(
                sync_db_session, telegram, transcriber,
                telegram_id=1, username=None, telegram_file_id="f1", chat_id=1,
            )

        fake_notify_delay.assert_not_called()
