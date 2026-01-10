"""Pytest configuration and shared fixtures."""

import gc
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


@pytest.fixture
def sample_clippings_file(tmp_path: Path) -> Path:
    """Create a sample My Clippings.txt file for testing."""
    content = """Test Book (Test Author)
- Your Highlight on page 42 | location 100-150 | Added on Monday, 15 January 2024 10:30:00

This is a sample highlight from the book.
==========
Another Book (Another Author)
- Your Highlight on page 10 | location 200-250 | Added on Tuesday, 16 January 2024 14:00:00

Another sample highlight with some interesting content.
==========
Test Book (Test Author)
- Your Bookmark on page 50 | location 300 | Added on Wednesday, 17 January 2024 09:00:00

==========
"""
    file_path = tmp_path / "My Clippings.txt"
    file_path.write_text(content, encoding="utf-8-sig")
    return file_path
