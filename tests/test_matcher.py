"""Tests for text matching functionality."""

import pytest

from anki_cards_from_kindle_highlights.matcher import (
    AmbiguousMatchException,
    BookMatcher,
    MatchResult,
    NoMatchException,
    _skeletonize,
)

SKELETONIZE_CASES = [
    # (input, expected_skeleton, expected_index_map_or_None)
    ("Hello, World!", "helloworld", None),
    ("Test 123 ABC", "test123abc", None),
    ("UPPERCASE lowercase MiXeD", "uppercaselowercasemixed", None),
    ("A-B-C", "abc", [0, 2, 4]),
    ("", "", []),
    ("!@#$%^&*()", "", []),
    ("Café résumé", "caférésumé", None),  # Accented chars are alphanumeric
]


@pytest.mark.parametrize("text,expected_skeleton,expected_index_map", SKELETONIZE_CASES)
def test_skeletonize(
    text: str, expected_skeleton: str, expected_index_map: list[int] | None
) -> None:
    """Test _skeletonize with various inputs."""
    skeleton, index_map = _skeletonize(text)

    assert skeleton == expected_skeleton
    if expected_index_map is not None:
        assert index_map == expected_index_map


class SimpleClipping:
    """Simple mock clipping for testing."""

    def __init__(self, content: str) -> None:
        self.content = content


class TestBookMatcher:
    """Tests for the BookMatcher class."""

    def test_exact_match(self) -> None:
        """Test exact matching of a clipping in book text."""
        matcher = BookMatcher("Test Author", "Test Book", None)
        matcher._text = (
            "This is the book text with a specific phrase that we want to match."
        )

        result = matcher.match(SimpleClipping("specific phrase"))

        assert isinstance(result, MatchResult)
        assert result.start > 0
        assert result.length > 0

    def test_no_match_raises_exception(self) -> None:
        """Test that NoMatchException is raised when no match is found."""
        matcher = BookMatcher("Author", "Title", None)
        matcher._text = "This is the book text."

        with pytest.raises(NoMatchException):
            matcher.match(SimpleClipping("nonexistent phrase that is not in the book"))

    def test_ambiguous_match_raises_exception(self) -> None:
        """Test that AmbiguousMatchException is raised for multiple matches."""
        matcher = BookMatcher("Author", "Title", None)
        matcher._text = "The word test appears here. And test appears again here."

        with pytest.raises(AmbiguousMatchException) as exc_info:
            matcher.match(SimpleClipping("test"))

        assert exc_info.value.match_count == 2

    def test_empty_content_raises_value_error(self) -> None:
        """Test that ValueError is raised for empty content."""
        matcher = BookMatcher("Author", "Title", None)
        matcher._text = "Book text."

        with pytest.raises(ValueError, match="no content"):
            matcher.match(SimpleClipping(""))

    def test_whitespace_only_content_raises_value_error(self) -> None:
        """Test that ValueError is raised for whitespace-only content."""
        matcher = BookMatcher("Author", "Title", None)
        matcher._text = "Book text."

        with pytest.raises(ValueError, match="no content"):
            matcher.match(SimpleClipping("   \n\t  "))

    def test_match_with_punctuation_differences(self) -> None:
        """Test matching when punctuation differs between clipping and book."""
        matcher = BookMatcher("Author", "Title", None)
        matcher._text = "The quick, brown fox jumps over the lazy dog."

        result = matcher.match(SimpleClipping("quick brown fox"))  # No comma
        assert isinstance(result, MatchResult)

    def test_match_with_case_differences(self) -> None:
        """Test matching when case differs between clipping and book."""
        matcher = BookMatcher("Author", "Title", None)
        matcher._text = "The QUICK Brown Fox Jumps Over The Lazy Dog."

        result = matcher.match(SimpleClipping("quick brown fox"))
        assert isinstance(result, MatchResult)
