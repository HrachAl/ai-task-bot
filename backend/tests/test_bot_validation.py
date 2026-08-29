import pytest

from app.bot.validation import ValidationError, validate_text_message, validate_voice_message


class TestValidateTextMessage:
    def test_strips_and_returns_clean_text(self):
        assert validate_text_message("  Buy milk  ") == "Buy milk"

    def test_none_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_text_message(None)

    def test_empty_string_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_text_message("")

    def test_whitespace_only_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_text_message("   ")

    def test_too_long_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_text_message("x" * 1001)

    def test_exactly_at_limit_is_accepted(self):
        text = "x" * 1000
        assert validate_text_message(text) == text


class TestValidateVoiceMessage:
    def test_valid_voice_passes(self):
        validate_voice_message(
            duration=30, file_size=1_000_000, max_duration_seconds=120, max_file_bytes=20_000_000
        )

    def test_missing_duration_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_voice_message(
                duration=None, file_size=100, max_duration_seconds=120, max_file_bytes=1000
            )

    def test_missing_file_size_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_voice_message(
                duration=10, file_size=None, max_duration_seconds=120, max_file_bytes=1000
            )

    def test_zero_duration_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_voice_message(
                duration=0, file_size=100, max_duration_seconds=120, max_file_bytes=1000
            )

    def test_too_long_duration_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_voice_message(
                duration=121, file_size=100, max_duration_seconds=120, max_file_bytes=1_000_000
            )

    def test_zero_file_size_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_voice_message(
                duration=10, file_size=0, max_duration_seconds=120, max_file_bytes=1000
            )

    def test_oversized_file_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_voice_message(
                duration=10,
                file_size=21_000_000,
                max_duration_seconds=120,
                max_file_bytes=20_000_000,
            )

    def test_exactly_at_duration_limit_is_accepted(self):
        validate_voice_message(
            duration=120, file_size=100, max_duration_seconds=120, max_file_bytes=1000
        )

    def test_exactly_at_size_limit_is_accepted(self):
        validate_voice_message(
            duration=10, file_size=1000, max_duration_seconds=120, max_file_bytes=1000
        )
