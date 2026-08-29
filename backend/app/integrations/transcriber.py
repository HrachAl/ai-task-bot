"""Speech-to-text integration. A `Transcriber` protocol keeps the worker's
business logic independent of the concrete provider, so tests can substitute
a fake implementation instead of calling the real OpenAI API.
"""

from typing import Protocol

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from app.core.config import get_settings
from app.exceptions import EmptyTranscriptionError, TranscriptionError


class Transcriber(Protocol):
    def transcribe(self, audio_bytes: bytes, filename: str) -> str: ...


class OpenAIWhisperTranscriber:
    def __init__(self, api_key: str, model: str = "whisper-1", language: str | None = None) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._language = language or None

    def transcribe(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        try:
            result = self._client.audio.transcriptions.create(
                model=self._model,
                file=(filename, audio_bytes),
                language=self._language,
                response_format="text",
            )
        except (APIConnectionError, APITimeoutError, RateLimitError, APIError) as exc:
            raise TranscriptionError(f"Whisper transcription failed: {exc}") from exc

        text = str(result).strip()
        if not text:
            raise EmptyTranscriptionError("Whisper returned an empty transcript")
        return text


def get_transcriber() -> Transcriber:
    settings = get_settings()
    return OpenAIWhisperTranscriber(
        api_key=settings.openai_api_key,
        model=settings.whisper_model,
        language=settings.whisper_language or None,
    )
