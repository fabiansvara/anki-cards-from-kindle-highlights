"""Tests for clippings parsing."""

from datetime import datetime
from pathlib import Path

from anki_cards_from_kindle_highlights.clippings import (
    Clipping,
    ClippingType,
    parse_clippings_file,
)


class TestParseClippingsRoundTrip:
    """Round-trip tests: serialize -> parse -> compare to original."""

    def test_round_trip_all_clippings(
        self, sample_clippings_file: Path, sample_clippings_data: list[Clipping]
    ) -> None:
        """Test that all clippings survive the round-trip."""
        parsed = parse_clippings_file(sample_clippings_file)
        assert len(parsed) == len(sample_clippings_data)

    def test_round_trip_highlights(
        self, sample_clippings_file: Path, sample_clippings_data: list[Clipping]
    ) -> None:
        """Test that highlights are parsed correctly."""
        parsed = parse_clippings_file(sample_clippings_file)
        expected_highlights = [
            c
            for c in sample_clippings_data
            if c.clipping_type == ClippingType.HIGHLIGHT
        ]
        parsed_highlights = [
            c for c in parsed if c.clipping_type == ClippingType.HIGHLIGHT
        ]

        assert len(parsed_highlights) == len(expected_highlights)
        for parsed_h, expected_h in zip(
            parsed_highlights, expected_highlights, strict=False
        ):
            assert parsed_h.content == expected_h.content
            assert parsed_h.book_title == expected_h.book_title
            assert parsed_h.author == expected_h.author

    def test_round_trip_bookmarks(
        self, sample_clippings_file: Path, sample_clippings_data: list[Clipping]
    ) -> None:
        """Test that bookmarks are parsed correctly."""
        parsed = parse_clippings_file(sample_clippings_file)
        expected_bookmarks = [
            c for c in sample_clippings_data if c.clipping_type == ClippingType.BOOKMARK
        ]
        parsed_bookmarks = [
            c for c in parsed if c.clipping_type == ClippingType.BOOKMARK
        ]

        assert len(parsed_bookmarks) == len(expected_bookmarks)
        for parsed_b, expected_b in zip(
            parsed_bookmarks, expected_bookmarks, strict=False
        ):
            assert parsed_b.page == expected_b.page
            assert parsed_b.location_start == expected_b.location_start

    def test_round_trip_locations(
        self, sample_clippings_file: Path, sample_clippings_data: list[Clipping]
    ) -> None:
        """Test that locations are parsed correctly."""
        parsed = parse_clippings_file(sample_clippings_file)

        for parsed_c, expected_c in zip(parsed, sample_clippings_data, strict=False):
            assert parsed_c.location_start == expected_c.location_start
            assert parsed_c.location_end == expected_c.location_end
            assert parsed_c.page == expected_c.page

    def test_round_trip_dates(
        self, sample_clippings_file: Path, sample_clippings_data: list[Clipping]
    ) -> None:
        """Test that dates are parsed correctly."""
        parsed = parse_clippings_file(sample_clippings_file)

        for parsed_c, expected_c in zip(parsed, sample_clippings_data, strict=False):
            assert parsed_c.date_added == expected_c.date_added


class TestParseClippingsEdgeCases:
    """Edge case tests for the parser."""

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
        from tests.conftest import clippings_to_file

        clipping = Clipping(
            book_title="Book Title (Series Name)",
            author="Author Name",
            clipping_type=ClippingType.HIGHLIGHT,
            page=1,
            location_start=10,
            location_end=20,
            date_added=datetime(2024, 1, 1, 12, 0, 0),
            content="Test content.",
        )
        file_path = tmp_path / "clippings.txt"
        clippings_to_file([clipping], file_path)

        parsed = parse_clippings_file(file_path)
        assert len(parsed) == 1
        assert parsed[0].book_title == clipping.book_title
        assert parsed[0].author == clipping.author

    def test_parse_no_author(self, tmp_path: Path) -> None:
        """Test parsing a clipping without author."""
        from tests.conftest import clippings_to_file

        clipping = Clipping(
            book_title="Book Without Author",
            author="",
            clipping_type=ClippingType.HIGHLIGHT,
            page=5,
            location_start=50,
            location_end=60,
            date_added=datetime(2024, 2, 1, 10, 0, 0),
            content="Content without author.",
        )
        file_path = tmp_path / "clippings.txt"
        clippings_to_file([clipping], file_path)

        parsed = parse_clippings_file(file_path)
        assert len(parsed) == 1
        assert parsed[0].book_title == clipping.book_title
        assert parsed[0].author == ""

    def test_parse_no_page(self, tmp_path: Path) -> None:
        """Test parsing a clipping without page number."""
        from tests.conftest import clippings_to_file

        clipping = Clipping(
            book_title="Book",
            author="Author",
            clipping_type=ClippingType.HIGHLIGHT,
            page=None,
            location_start=100,
            location_end=110,
            date_added=datetime(2024, 3, 1, 15, 0, 0),
            content="Content without page.",
        )
        file_path = tmp_path / "clippings.txt"
        clippings_to_file([clipping], file_path)

        parsed = parse_clippings_file(file_path)
        assert len(parsed) == 1
        assert parsed[0].page is None
        assert parsed[0].location_start == clipping.location_start

    def test_parse_note_type(self, tmp_path: Path) -> None:
        """Test parsing a note clipping type."""
        from tests.conftest import clippings_to_file

        clipping = Clipping(
            book_title="Book",
            author="Author",
            clipping_type=ClippingType.NOTE,
            page=10,
            location_start=200,
            location_end=None,
            date_added=datetime(2024, 4, 1, 8, 0, 0),
            content="This is a note.",
        )
        file_path = tmp_path / "clippings.txt"
        clippings_to_file([clipping], file_path)

        parsed = parse_clippings_file(file_path)
        assert len(parsed) == 1
        assert parsed[0].clipping_type == ClippingType.NOTE
        assert parsed[0].content == clipping.content
