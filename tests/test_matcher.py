"""Tests for text matching functionality."""

import pytest

from anki_cards_from_kindle_highlights.matcher import (
    AmbiguousMatchException,
    BookMatcher,
    MatchResult,
    NoMatchException,
    _skeletonize,
)


class TestSkeletonize:
    """Tests for the _skeletonize function."""

    def test_basic_skeletonization(self) -> None:
        """Test basic text skeletonization."""
        text = "Hello, World!"
        skeleton, index_map = _skeletonize(text)

        assert skeleton == "helloworld"
        assert len(index_map) == 10

    def test_preserves_alphanumeric(self) -> None:
        """Test that only alphanumeric characters are kept."""
        text = "Test 123 ABC"
        skeleton, index_map = _skeletonize(text)

        assert skeleton == "test123abc"

    def test_lowercase_conversion(self) -> None:
        """Test that text is converted to lowercase."""
        text = "UPPERCASE lowercase MiXeD"
        skeleton, _ = _skeletonize(text)

        assert skeleton == "uppercaselowercasemixed"

    def test_index_map_correctness(self) -> None:
        """Test that index map correctly maps to original positions."""
        text = "A-B-C"
        skeleton, index_map = _skeletonize(text)

        assert skeleton == "abc"
        assert index_map == [0, 2, 4]  # Positions of A, B, C in original

    def test_empty_string(self) -> None:
        """Test skeletonization of empty string."""
        skeleton, index_map = _skeletonize("")

        assert skeleton == ""
        assert index_map == []

    def test_no_alphanumeric(self) -> None:
        """Test text with no alphanumeric characters."""
        text = "!@#$%^&*()"
        skeleton, index_map = _skeletonize(text)

        assert skeleton == ""
        assert index_map == []

    def test_unicode_characters(self) -> None:
        """Test handling of unicode characters."""
        text = "Café résumé"
        skeleton, index_map = _skeletonize(text)

        # Should keep alphanumeric, accented chars are alphanumeric
        assert "caf" in skeleton
        assert "r" in skeleton


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


class TestMatchResult:
    """Tests for MatchResult dataclass."""

    def test_match_result_creation(self) -> None:
        """Test creating a MatchResult."""
        result = MatchResult(start=10, length=20)

        assert result.start == 10
        assert result.length == 20
