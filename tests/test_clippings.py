"""Tests for clippings parsing."""

from datetime import datetime
from pathlib import Path

from anki_cards_from_kindle_highlights.clippings import (
    Clipping,
    ClippingType,
    parse_clippings_file,
)


class TestParseClippingsFile:
    """Tests for parse_clippings_file function."""

    def test_parse_valid_file(self, sample_clippings_file: Path) -> None:
        """Test parsing a valid clippings file."""
        clippings = parse_clippings_file(sample_clippings_file)

        # Should have 3 entries (2 highlights + 1 bookmark)
        assert len(clippings) == 3

    def test_parse_highlights_content(self, sample_clippings_file: Path) -> None:
        """Test that highlights have correct content."""
        clippings = parse_clippings_file(sample_clippings_file)
        highlights = [c for c in clippings if c.clipping_type == ClippingType.HIGHLIGHT]

        assert len(highlights) == 2
        assert highlights[0].content == "This is a sample highlight from the book."
        assert (
            highlights[1].content
            == "Another sample highlight with some interesting content."
        )

    def test_parse_book_and_author(self, sample_clippings_file: Path) -> None:
        """Test that book title and author are parsed correctly."""
        clippings = parse_clippings_file(sample_clippings_file)

        assert clippings[0].book_title == "Test Book"
        assert clippings[0].author == "Test Author"
        assert clippings[1].book_title == "Another Book"
        assert clippings[1].author == "Another Author"

    def test_parse_location(self, sample_clippings_file: Path) -> None:
        """Test that location is parsed correctly."""
        clippings = parse_clippings_file(sample_clippings_file)

        assert clippings[0].location_start == 100
        assert clippings[0].location_end == 150
        assert clippings[0].page == 42

    def test_parse_date(self, sample_clippings_file: Path) -> None:
        """Test that date is parsed correctly."""
        clippings = parse_clippings_file(sample_clippings_file)

        assert clippings[0].date_added == datetime(2024, 1, 15, 10, 30, 0)

    def test_parse_bookmark(self, sample_clippings_file: Path) -> None:
        """Test that bookmarks are parsed correctly."""
        clippings = parse_clippings_file(sample_clippings_file)
        bookmarks = [c for c in clippings if c.clipping_type == ClippingType.BOOKMARK]

        assert len(bookmarks) == 1
        assert bookmarks[0].page == 50
        assert bookmarks[0].location_start == 300

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        """Test parsing a file that doesn't exist."""
        fake_path = tmp_path / "nonexistent.txt"
        clippings = parse_clippings_file(fake_path)
        assert clippings == []

    def test_parse_empty_file(self, tmp_path: Path) -> None:
        """Test parsing an empty file."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("", encoding="utf-8")
        clippings = parse_clippings_file(empty_file)
        assert clippings == []

    def test_parse_title_with_parentheses(self, tmp_path: Path) -> None:
        """Test parsing a title that contains parentheses."""
        content = """Book Title (Series Name) (Author Name)
- Your Highlight on page 1 | location 10-20 | Added on Monday, 1 January 2024 12:00:00

Test content.
==========
"""
        file_path = tmp_path / "clippings.txt"
        file_path.write_text(content, encoding="utf-8-sig")

        clippings = parse_clippings_file(file_path)
        assert len(clippings) == 1
        assert clippings[0].book_title == "Book Title (Series Name)"
        assert clippings[0].author == "Author Name"


class TestClippingDataclass:
    """Tests for the Clipping dataclass."""

    def test_clipping_creation(self) -> None:
        """Test creating a Clipping object."""
        clipping = Clipping(
            book_title="Test Book",
            author="Test Author",
            clipping_type=ClippingType.HIGHLIGHT,
            page=10,
            location_start=100,
            location_end=110,
            date_added=datetime(2024, 1, 1),
            content="Test content",
        )

        assert clipping.book_title == "Test Book"
        assert clipping.author == "Test Author"
        assert clipping.clipping_type == ClippingType.HIGHLIGHT

    def test_clipping_with_empty_author(self) -> None:
        """Test clipping with empty author."""
        clipping = Clipping(
            book_title="Test Book",
            author="",
            clipping_type=ClippingType.NOTE,
            page=None,
            location_start=50,
            location_end=None,
            date_added=datetime(2024, 1, 1),
            content="A note",
        )

        assert clipping.author == ""
