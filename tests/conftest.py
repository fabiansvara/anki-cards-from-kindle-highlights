"""Pytest configuration and shared fixtures."""

import gc
import sqlite3
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anki_cards_from_kindle_highlights.clippings import Clipping, ClippingType
from anki_cards_from_kindle_highlights.db import ClippingsDatabase


@pytest.fixture
def temp_db(tmp_path: Path) -> Generator[ClippingsDatabase, None, None]:
    """Create an ephemeral test database.

    Uses pytest's tmp_path fixture which handles cleanup automatically,
    avoiding Windows file locking issues.
    """
    db_path = tmp_path / "test_clippings.db"
    db = ClippingsDatabase(db_path)
    yield db
    db.close()
    # Force garbage collection to release any lingering SQLite handles
    gc.collect()


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create an ephemeral database path for testing.

    Uses pytest's tmp_path fixture which handles cleanup automatically.
    """
    return tmp_path / "test_clippings.db"


@pytest.fixture
def sample_clipping() -> Clipping:
    """Create a sample clipping for testing."""
    return Clipping(
        book_title="Test Book",
        author="Test Author",
        clipping_type=ClippingType.HIGHLIGHT,
        page=42,
        location_start=100,
        location_end=150,
        date_added=datetime(2024, 1, 15, 10, 30, 0),
        content="This is a sample highlight from the book.",
    )


@pytest.fixture
def sample_clippings() -> list[Clipping]:
    """Create multiple sample clippings for testing."""
    return [
        Clipping(
            book_title="Book One",
            author="Author One",
            clipping_type=ClippingType.HIGHLIGHT,
            page=10,
            location_start=100,
            location_end=110,
            date_added=datetime(2024, 1, 15, 10, 0, 0),
            content="First highlight from book one.",
        ),
        Clipping(
            book_title="Book One",
            author="Author One",
            clipping_type=ClippingType.HIGHLIGHT,
            page=20,
            location_start=200,
            location_end=220,
            date_added=datetime(2024, 1, 15, 11, 0, 0),
            content="Second highlight from book one.",
        ),
        Clipping(
            book_title="Book Two",
            author="Author Two",
            clipping_type=ClippingType.HIGHLIGHT,
            page=5,
            location_start=50,
            location_end=60,
            date_added=datetime(2024, 1, 16, 9, 0, 0),
            content="Highlight from book two.",
        ),
    ]


@pytest.fixture
def mock_openai_response() -> dict[str, str]:
    """Create a mock OpenAI API response."""
    return {
        "pattern": "MENTAL_MODEL",
        "front": "What is the key insight from this passage?",
        "back": "The key insight is that testing is important.",
    }


@pytest.fixture
def mock_openai_client(mock_openai_response: dict[str, str]) -> MagicMock:
    """Create a mock OpenAI client."""
    mock_client = MagicMock()

    # Mock the synchronous client
    mock_parsed = MagicMock()
    mock_parsed.pattern = mock_openai_response["pattern"]
    mock_parsed.front = mock_openai_response["front"]
    mock_parsed.back = mock_openai_response["back"]

    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_parsed

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client.beta.chat.completions.parse.return_value = mock_completion

    return mock_client


@pytest.fixture
def mock_anki_connect() -> Generator[MagicMock, None, None]:
    """Mock the AnkiConnect requests."""
    with patch("anki_cards_from_kindle_highlights.anki.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": None, "error": None}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        yield mock_post


def _create_calibre_schema(db_path: Path) -> None:
    """Create the basic Calibre database schema."""

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


@pytest.fixture
def empty_calibre(tmp_path: Path) -> Path:
    """Create an empty Calibre database with just the schema."""
    db_path = tmp_path / "metadata.db"
    _create_calibre_schema(db_path)
    return tmp_path


@pytest.fixture
def one_book_calibre(tmp_path: Path) -> Path:
    """Create a Calibre database with one book with EPUB format."""
    import sqlite3

    db_path = tmp_path / "metadata.db"
    _create_calibre_schema(db_path)

    conn = sqlite3.connect(db_path)
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
    return tmp_path


@pytest.fixture
def multi_format_calibre(tmp_path: Path) -> Path:
    """Create a Calibre database with one book in multiple formats."""
    import sqlite3

    db_path = tmp_path / "metadata.db"
    _create_calibre_schema(db_path)

    conn = sqlite3.connect(db_path)
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
    return tmp_path


def clipping_to_kindle_format(clipping: Clipping) -> str:
    """Serialize a Clipping object to Kindle's My Clippings.txt format."""
    # Header: "Book Title (Author)" or just "Book Title"
    if clipping.author:
        header = f"{clipping.book_title} ({clipping.author})"
    else:
        header = clipping.book_title

    # Metadata line: "- Your Highlight on page X | location Y-Z | Added on ..."
    type_str = clipping.clipping_type.value
    parts = [f"- Your {type_str}"]

    if clipping.page is not None:
        parts.append(f"on page {clipping.page}")

    if clipping.location_end is not None:
        parts.append(f"| location {clipping.location_start}-{clipping.location_end}")
    else:
        parts.append(f"| location {clipping.location_start}")

    date_str = clipping.date_added.strftime("%A, %d %B %Y %H:%M:%S")
    parts.append(f"| Added on {date_str}")

    metadata = " ".join(parts)

    # Content (may be empty for bookmarks)
    return f"{header}\n{metadata}\n\n{clipping.content}\n=========="


def clippings_to_file(clippings: list[Clipping], file_path: Path) -> None:
    """Write clippings to a file in Kindle format."""
    content = "\n".join(clipping_to_kindle_format(c) for c in clippings) + "\n"
    file_path.write_text(content, encoding="utf-8-sig")


# Sample clippings used as the single source of truth for tests
SAMPLE_CLIPPINGS = [
    Clipping(
        book_title="Test Book",
        author="Test Author",
        clipping_type=ClippingType.HIGHLIGHT,
        page=42,
        location_start=100,
        location_end=150,
        date_added=datetime(2024, 1, 15, 10, 30, 0),
        content="This is a sample highlight from the book.",
    ),
    Clipping(
        book_title="Another Book",
        author="Another Author",
        clipping_type=ClippingType.HIGHLIGHT,
        page=10,
        location_start=200,
        location_end=250,
        date_added=datetime(2024, 1, 16, 14, 0, 0),
        content="Another sample highlight with some interesting content.",
    ),
    Clipping(
        book_title="Test Book",
        author="Test Author",
        clipping_type=ClippingType.BOOKMARK,
        page=50,
        location_start=300,
        location_end=None,
        date_added=datetime(2024, 1, 17, 9, 0, 0),
        content="",
    ),
]


@pytest.fixture
def sample_clippings_data() -> list[Clipping]:
    """Return the sample clippings (source of truth for round-trip tests)."""
    return SAMPLE_CLIPPINGS.copy()


@pytest.fixture
def sample_clippings_file(
    tmp_path: Path, sample_clippings_data: list[Clipping]
) -> Path:
    """Create a sample My Clippings.txt file from sample clippings."""
    file_path = tmp_path / "My Clippings.txt"
    clippings_to_file(sample_clippings_data, file_path)
    return file_path
