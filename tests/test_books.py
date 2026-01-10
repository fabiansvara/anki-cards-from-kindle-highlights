"""Tests for book metadata and content extraction."""

import sqlite3
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

    def test_preserves_structure(self) -> None:
        """Test that some structure is preserved via Markdown."""
        html = "<h1>Title</h1><p>Paragraph</p>"
        text = _html_to_text(html)

        assert "Title" in text
        assert "Paragraph" in text


class TestBook:
    """Tests for the Book class."""

    def test_book_creation(self) -> None:
        """Test creating a Book object."""
        book = Book(author="Test Author", title="Test Title", epub_path=None)

        assert book.author == "Test Author"
        assert book.title == "Test Title"
        assert book.epub_path is None

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

    def test_reads_empty_calibre_db(self, tmp_path: Path) -> None:
        """Test reading an empty Calibre database."""
        # Create a minimal Calibre-like database
        db_path = tmp_path / "metadata.db"
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT,
                path TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY,
                book INTEGER,
                author INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE data (
                id INTEGER PRIMARY KEY,
                book INTEGER,
                name TEXT,
                format TEXT
            )
        """)
        conn.commit()
        conn.close()

        result = books_from_calibre(tmp_path)

        assert result == {}

    def test_reads_books_with_epub(self, tmp_path: Path) -> None:
        """Test reading books with EPUB format."""
        # Create a minimal Calibre-like database with a book
        db_path = tmp_path / "metadata.db"
        conn = sqlite3.connect(db_path)

        conn.execute("""
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT,
                path TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY,
                book INTEGER,
                author INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE data (
                id INTEGER PRIMARY KEY,
                book INTEGER,
                name TEXT,
                format TEXT
            )
        """)

        # Insert test data
        conn.execute(
            "INSERT INTO books (id, title, path) VALUES (1, 'Test Book', 'Author/Test Book (1)')"
        )
        conn.execute("INSERT INTO authors (id, name) VALUES (1, 'Test Author')")
        conn.execute("INSERT INTO books_authors_link (book, author) VALUES (1, 1)")
        conn.execute(
            "INSERT INTO data (book, name, format) VALUES (1, 'Test Book', 'EPUB')"
        )
        conn.commit()
        conn.close()

        result = books_from_calibre(tmp_path)

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

    def test_prefers_epub_over_other_formats(self, tmp_path: Path) -> None:
        """Test that EPUB format is preferred over others."""
        db_path = tmp_path / "metadata.db"
        conn = sqlite3.connect(db_path)

        conn.execute("""
            CREATE TABLE books (
                id INTEGER PRIMARY KEY,
                title TEXT,
                path TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE authors (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE books_authors_link (
                id INTEGER PRIMARY KEY,
                book INTEGER,
                author INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE data (
                id INTEGER PRIMARY KEY,
                book INTEGER,
                name TEXT,
                format TEXT
            )
        """)

        # Insert test data with multiple formats
        conn.execute(
            "INSERT INTO books (id, title, path) VALUES (1, 'Multi Format', 'Author/Multi Format (1)')"
        )
        conn.execute("INSERT INTO authors (id, name) VALUES (1, 'Author')")
        conn.execute("INSERT INTO books_authors_link (book, author) VALUES (1, 1)")
        conn.execute(
            "INSERT INTO data (book, name, format) VALUES (1, 'Multi Format', 'PDF')"
        )
        conn.execute(
            "INSERT INTO data (book, name, format) VALUES (1, 'Multi Format', 'EPUB')"
        )
        conn.execute(
            "INSERT INTO data (book, name, format) VALUES (1, 'Multi Format', 'MOBI')"
        )
        conn.commit()
        conn.close()

        result = books_from_calibre(tmp_path)

        assert len(result) == 1
        book = result[("Author", "Multi Format")]
        assert book.epub_path is not None
        assert book.epub_path.endswith(".epub")
