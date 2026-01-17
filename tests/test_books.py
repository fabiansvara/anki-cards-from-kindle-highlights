"""Tests for book metadata and content extraction."""

from pathlib import Path

import pytest

from anki_cards_from_kindle_highlights.books import (
    Book,
    _html_to_text,
    books_from_calibre,
)


class TestHtmlToText:
    """Tests for _html_to_text function."""

    def test_simple_html(self) -> None:
        """Test converting simple HTML to text."""
        html = "<p>Hello World</p>"
        text = _html_to_text(html)

        assert "Hello World" in text

    def test_strips_tags(self) -> None:
        """Test that HTML tags are stripped."""
        html = "<div><p><strong>Bold</strong> and <em>italic</em></p></div>"
        text = _html_to_text(html)

        assert "Bold" in text
        assert "italic" in text
        assert "<" not in text
        assert ">" not in text

    def test_handles_bytes(self) -> None:
        """Test handling of bytes input."""
        html = b"<p>Hello from bytes</p>"
        text = _html_to_text(html)

        assert "Hello from bytes" in text


class TestBook:
    """Tests for the Book class."""

    def test_book_repr(self) -> None:
        """Test Book string representation."""
        book = Book(author="Author", title="Title", epub_path="/path/to/book.epub")
        repr_str = repr(book)

        assert "Author" in repr_str
        assert "Title" in repr_str
        assert "/path/to/book.epub" in repr_str

    def test_text_returns_none_without_epub(self) -> None:
        """Test that text property returns None when no epub path."""
        book = Book(author="Author", title="Title", epub_path=None)

        assert book.text is None

    def test_text_returns_none_for_nonexistent_epub(self) -> None:
        """Test that text property returns None for nonexistent file."""
        book = Book(author="Author", title="Title", epub_path="/nonexistent/book.epub")

        assert book.text is None

    def test_text_is_cached(self) -> None:
        """Test that text property caches its result."""
        book = Book(author="Author", title="Title", epub_path=None)

        # Manually set cached text
        book._text = "Cached content"

        # Should return cached value
        assert book.text == "Cached content"


class TestBooksFromCalibre:
    """Tests for books_from_calibre function."""

    def test_raises_for_nonexistent_db(self, tmp_path: Path) -> None:
        """Test that FileNotFoundError is raised for missing metadata.db."""
        with pytest.raises(FileNotFoundError, match="Calibre database not found"):
            books_from_calibre(tmp_path)

    def test_reads_empty_calibre_db(self, empty_calibre: Path) -> None:
        """Test reading an empty Calibre database."""
        result = books_from_calibre(empty_calibre)
        assert result == {}

    def test_reads_books_with_epub(self, one_book_calibre: Path) -> None:
        """Test reading books with EPUB format."""
        result = books_from_calibre(one_book_calibre)

        assert len(result) == 1
        key = ("Test Author", "Test Book")
        assert key in result
        assert result[key].author == "Test Author"
        assert result[key].title == "Test Book"
        # Check path components in OS-independent way
        epub_path_str = result[key].epub_path
        assert epub_path_str is not None
        epub_path = Path(epub_path_str)
        assert epub_path.name == "Test Book.epub"
        assert "Test Book (1)" in epub_path.parts

    def test_prefers_epub_over_other_formats(self, multi_format_calibre: Path) -> None:
        """Test that EPUB format is preferred over others."""
        result = books_from_calibre(multi_format_calibre)

        assert len(result) == 1
        book = result[("Author", "Multi Format")]
        assert book.epub_path is not None
        assert book.epub_path.endswith(".epub")
