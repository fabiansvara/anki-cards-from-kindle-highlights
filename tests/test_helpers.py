"""Tests for CLI helper functions."""

from anki_cards_from_kindle_highlights.cli.helpers import abbreviate, get_prompt


class TestAbbreviate:
    """Tests for the abbreviate function."""

    def test_short_text_unchanged(self) -> None:
        """Test that short text is not abbreviated."""
        text = "Short text"
        result = abbreviate(text, max_len=50)
        assert result == "Short text"

    def test_long_text_abbreviated(self) -> None:
        """Test that long text is abbreviated with ellipsis."""
        text = "This is a very long text that should be abbreviated"
        result = abbreviate(text, max_len=20)

        assert len(result) == 20
        assert result.endswith("...")

    def test_exact_length_unchanged(self) -> None:
        """Test that text at exact max length is unchanged."""
        text = "Exactly ten"  # 11 chars
        result = abbreviate(text, max_len=11)
        assert result == text

    def test_none_returns_empty(self) -> None:
        """Test that None input returns empty string."""
        result = abbreviate(None)
        assert result == ""

    def test_newlines_removed(self) -> None:
        """Test that newlines are replaced with spaces."""
        text = "Line one\nLine two\nLine three"
        result = abbreviate(text, max_len=100)
        assert "\n" not in result
        assert result == "Line one Line two Line three"

    def test_whitespace_stripped(self) -> None:
        """Test that leading/trailing whitespace is stripped."""
        text = "  text with spaces  "
        result = abbreviate(text)
        assert result == "text with spaces"

    def test_default_max_len(self) -> None:
        """Test the default max_len of 50."""
        text = "x" * 100
        result = abbreviate(text)
        assert len(result) == 50


class TestGetPrompt:
    """Tests for the get_prompt function."""

    def test_returns_string(self) -> None:
        """Test that get_prompt returns a non-empty string."""
        prompt = get_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_contains_key_instructions(self) -> None:
        """Test that prompt contains expected content."""
        prompt = get_prompt()
        # The prompt should mention Anki cards or similar
        assert "anki" in prompt.lower() or "card" in prompt.lower()
