class TaskNotFoundError(Exception):
    """Raised when a task id does not exist."""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


class VoiceProcessingError(Exception):
    """Base class for anything that can go wrong in the voice pipeline."""


class TelegramAPIError(VoiceProcessingError):
    """Telegram API call failed (network error, 5xx, rate limit). Retryable."""


class AudioDownloadError(TelegramAPIError):
    """Downloading the voice file from Telegram failed. Retryable."""


class InvalidAudioError(VoiceProcessingError):
    """The audio is missing, empty, or otherwise unusable. Not retryable."""


class TranscriptionError(VoiceProcessingError):
    """The Whisper/OpenAI API call itself failed (network, 5xx, rate limit). Retryable."""


class EmptyTranscriptionError(VoiceProcessingError):
    """Whisper returned no text (e.g. silence). Retrying won't help. Not retryable."""
