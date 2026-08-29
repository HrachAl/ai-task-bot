"""Pure validation helpers for incoming Telegram messages — kept free of
aiogram/network types so they're trivial to unit test."""

MAX_TEXT_LENGTH = 1000


class ValidationError(Exception):
    """Raised for malformed or out-of-bounds input the bot should reject
    before doing any work (no HTTP call, no Celery job)."""


def validate_text_message(text: str | None) -> str:
    if text is None:
        raise ValidationError("Message has no text.")
    cleaned = text.strip()
    if not cleaned:
        raise ValidationError("Message is empty.")
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise ValidationError(f"Message is too long (max {MAX_TEXT_LENGTH} characters).")
    return cleaned


def validate_voice_message(
    *,
    duration: int | None,
    file_size: int | None,
    max_duration_seconds: int,
    max_file_bytes: int,
) -> None:
    if duration is None or file_size is None:
        raise ValidationError("Voice message is missing metadata.")
    if duration <= 0:
        raise ValidationError("Voice message has an invalid duration.")
    if duration > max_duration_seconds:
        raise ValidationError(
            f"Voice message is too long (max {max_duration_seconds // 60} minute(s))."
        )
    if file_size <= 0:
        raise ValidationError("Voice message appears to be empty.")
    if file_size > max_file_bytes:
        raise ValidationError(
            f"Voice message is too large (max {max_file_bytes // (1024 * 1024)} MB)."
        )
