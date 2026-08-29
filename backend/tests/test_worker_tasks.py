from unittest.mock import MagicMock

import pytest

from app.exceptions import (
    AudioDownloadError,
    EmptyTranscriptionError,
    InvalidAudioError,
    TelegramAPIError,
    TranscriptionError,
)
from app.worker import tasks as worker_tasks
from app.worker.tasks import notify_telegram_task, transcribe_voice_task


@pytest.fixture(autouse=True)
def fake_notify_delay(monkeypatch):
    """Every test in this module runs against a real Celery task object, so
    without this, `.delay()` would try to talk to the real broker. Tests that
    care about the call assert on this mock directly."""
    mock = MagicMock()
    monkeypatch.setattr(notify_telegram_task, "delay", mock)
    return mock


class FakeTelegramClient:
    def __init__(self, *, file_path="voice/f.oga", audio=b"bytes"):
        self.file_path = file_path
        self.audio = audio

    def get_file_path(self, file_id: str) -> str:
        return self.file_path

    def download_file(self, file_path: str) -> bytes:
        return self.audio


class FakeTranscriber:
    def __init__(self, *, text: str = "Buy milk"):
        self.text = text

    def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        return self.text


class TestRetryPolicyConfiguration:
    """The retryable/non-retryable split is what makes 'worker failures' and
    'transcription failures' recover correctly without hammering a permanently
    broken input (bad audio, silence) — verify the wiring, not real sleeps."""

    def test_transient_errors_are_retried(self):
        assert AudioDownloadError in transcribe_voice_task.autoretry_for
        assert TranscriptionError in transcribe_voice_task.autoretry_for

    def test_permanent_errors_are_not_retried(self):
        assert InvalidAudioError not in transcribe_voice_task.autoretry_for
        assert EmptyTranscriptionError not in transcribe_voice_task.autoretry_for

    def test_retry_has_a_bounded_backoff(self):
        assert transcribe_voice_task.max_retries == 3
        assert transcribe_voice_task.retry_backoff
        assert transcribe_voice_task.retry_jitter is True


class TestTranscribeVoiceTaskHappyPath:
    def test_apply_creates_task_and_enqueues_notification(
        self, monkeypatch, sync_db_session, fake_notify_delay
    ):
        fake_telegram = FakeTelegramClient()
        fake_transcriber = FakeTranscriber(text="Buy milk")

        monkeypatch.setattr(worker_tasks, "SyncSessionLocal", lambda: sync_db_session)
        monkeypatch.setattr(worker_tasks, "get_telegram_client", lambda: fake_telegram)
        monkeypatch.setattr(worker_tasks, "get_transcriber", lambda: fake_transcriber)
        # Prevent the fixture's own rollback-on-close from firing mid-task.
        monkeypatch.setattr(sync_db_session, "close", lambda: None)

        result = transcribe_voice_task.apply(
            kwargs={
                "telegram_id": 1,
                "username": "hrach",
                "telegram_file_id": "file-1",
                "chat_id": 1,
                "ack_message_id": 9,
            }
        )

        assert result.successful()
        fake_notify_delay.assert_called_once()
        args, kwargs = fake_notify_delay.call_args
        assert args[0] == 1
        assert kwargs["message_id"] == 9


class TestVoiceTaskOnFailure:
    def test_known_error_maps_to_friendly_message(self, fake_notify_delay):
        transcribe_voice_task.on_failure(
            AudioDownloadError("boom"),
            "task-id-1",
            (),
            {"chat_id": 55, "ack_message_id": 3},
            None,
        )

        fake_notify_delay.assert_called_once()
        args, kwargs = fake_notify_delay.call_args
        assert args[0] == 55
        assert "download" in args[1].lower()
        assert kwargs["message_id"] == 3

    def test_unknown_error_uses_default_message(self, fake_notify_delay):
        transcribe_voice_task.on_failure(
            RuntimeError("something unexpected"),
            "task-id-2",
            (),
            {"chat_id": 55, "ack_message_id": None},
            None,
        )

        args, _kwargs = fake_notify_delay.call_args
        assert args[1] == worker_tasks.DEFAULT_FAILURE_MESSAGE

    def test_missing_chat_id_does_not_crash(self, fake_notify_delay):
        # Should return without even trying to queue a notification.
        transcribe_voice_task.on_failure(AudioDownloadError("boom"), "task-id-3", (), {}, None)
        fake_notify_delay.assert_not_called()

    def test_enqueue_failure_is_swallowed(self, fake_notify_delay):
        fake_notify_delay.side_effect = RuntimeError("broker is down")

        # Must not raise — a failed attempt to queue the failure notification
        # must not crash the worker's own failure handling.
        transcribe_voice_task.on_failure(
            AudioDownloadError("boom"), "task-id-4", (), {"chat_id": 1}, None
        )


class TestNotifyTelegramTask:
    """The notification is its own retryable, queued job — decoupled from
    whatever produced it — so a transient Telegram/network error is retried
    instead of being silently dropped."""

    def test_retry_policy_configuration(self):
        assert TelegramAPIError in notify_telegram_task.autoretry_for
        assert notify_telegram_task.max_retries == 3
        assert notify_telegram_task.retry_backoff
        assert notify_telegram_task.retry_jitter is True

    def test_edits_the_placeholder_when_message_id_given(self, monkeypatch):
        client = MagicMock()
        monkeypatch.setattr(worker_tasks, "get_telegram_client", lambda: client)

        notify_telegram_task._orig_run(1, "done", message_id=42)

        client.edit_message_text.assert_called_once_with(1, 42, "done", reply_markup=None)
        client.send_message.assert_not_called()

    def test_sends_a_fresh_message_when_no_message_id(self, monkeypatch):
        client = MagicMock()
        monkeypatch.setattr(worker_tasks, "get_telegram_client", lambda: client)

        notify_telegram_task._orig_run(1, "done", message_id=None)

        client.send_message.assert_called_once_with(1, "done", reply_markup=None)

    def test_falls_back_to_send_message_when_edit_fails(self, monkeypatch):
        client = MagicMock()
        client.edit_message_text.side_effect = TelegramAPIError("message to edit not found")
        monkeypatch.setattr(worker_tasks, "get_telegram_client", lambda: client)

        notify_telegram_task._orig_run(1, "done", message_id=42)

        client.send_message.assert_called_once_with(1, "done", reply_markup=None)

    def test_forwards_reply_markup_to_the_telegram_client(self, monkeypatch):
        client = MagicMock()
        monkeypatch.setattr(worker_tasks, "get_telegram_client", lambda: client)
        keyboard = {"inline_keyboard": [[{"text": "Pending", "callback_data": "status:1:pending"}]]}

        notify_telegram_task._orig_run(1, "done", message_id=42, reply_markup=keyboard)

        client.edit_message_text.assert_called_once_with(1, 42, "done", reply_markup=keyboard)

    def test_raises_when_both_edit_and_fallback_fail(self, monkeypatch):
        """Left to propagate so Celery's autoretry_for can catch it and
        retry the whole job later instead of losing the notification."""
        client = MagicMock()
        client.edit_message_text.side_effect = TelegramAPIError("timeout")
        client.send_message.side_effect = TelegramAPIError("timeout")
        monkeypatch.setattr(worker_tasks, "get_telegram_client", lambda: client)

        with pytest.raises(TelegramAPIError):
            notify_telegram_task._orig_run(1, "done", message_id=42)
