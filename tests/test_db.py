"""Tests for database operations."""

from anki_cards_from_kindle_highlights.clippings import Clipping
from anki_cards_from_kindle_highlights.db import ClippingsDatabase


class TestClippingsDatabase:
    """Tests for ClippingsDatabase class."""

    def test_insert_clipping(
        self, temp_db: ClippingsDatabase, sample_clipping: Clipping
    ) -> None:
        """Test inserting a clipping into the database."""
        row_id = temp_db.insert_clipping(sample_clipping)

        assert row_id is not None
        assert row_id > 0

    def test_insert_duplicate_clipping(
        self, temp_db: ClippingsDatabase, sample_clipping: Clipping
    ) -> None:
        """Test that duplicate clippings are rejected."""
        row_id1 = temp_db.insert_clipping(sample_clipping)
        row_id2 = temp_db.insert_clipping(sample_clipping)

        assert row_id1 is not None
        assert row_id2 is None  # Duplicate should return None

    def test_get_all_records(
        self, temp_db: ClippingsDatabase, sample_clippings: list[Clipping]
    ) -> None:
        """Test getting all records from the database."""
        for clipping in sample_clippings:
            temp_db.insert_clipping(clipping)

        records = temp_db.get_all_records()
        assert len(records) == 3

    def test_get_record_by_id(
        self, temp_db: ClippingsDatabase, sample_clipping: Clipping
    ) -> None:
        """Test getting a record by its ID."""
        row_id = temp_db.insert_clipping(sample_clipping)
        assert row_id is not None

        record = temp_db.get_record_by_id(row_id)

        assert record is not None
        assert record.id == row_id
        assert record.book_title == sample_clipping.book_title
        assert record.author == sample_clipping.author
        assert record.content == sample_clipping.content

    def test_get_record_by_invalid_id(self, temp_db: ClippingsDatabase) -> None:
        """Test getting a record with an invalid ID."""
        record = temp_db.get_record_by_id(9999)
        assert record is None

    def test_update_card_data(
        self, temp_db: ClippingsDatabase, sample_clipping: Clipping
    ) -> None:
        """Test updating card data for a clipping."""
        row_id = temp_db.insert_clipping(sample_clipping)
        assert row_id is not None

        temp_db.update_card_data(
            record_id=row_id,
            pattern="MENTAL_MODEL",
            front="What is the key insight?",
            back="The answer is 42.",
        )

        record = temp_db.get_record_by_id(row_id)
        assert record is not None
        assert record.pattern == "MENTAL_MODEL"
        assert record.front == "What is the key insight?"
        assert record.back == "The answer is 42."
        assert record.generated_at is not None

    def test_mark_synced(
        self, temp_db: ClippingsDatabase, sample_clipping: Clipping
    ) -> None:
        """Test marking a record as synced."""
        row_id = temp_db.insert_clipping(sample_clipping)
        assert row_id is not None

        # Initially not synced
        record = temp_db.get_record_by_id(row_id)
        assert record is not None
        assert record.synced_to_anki is False

        temp_db.mark_synced(row_id)

        record = temp_db.get_record_by_id(row_id)
        assert record is not None
        assert record.synced_to_anki is True

    def test_get_books_with_unprocessed(
        self, temp_db: ClippingsDatabase, sample_clippings: list[Clipping]
    ) -> None:
        """Test getting books with unprocessed clippings."""
        for clipping in sample_clippings:
            temp_db.insert_clipping(clipping)

        books = temp_db.get_books_with_unprocessed()

        assert len(books) == 2  # Book One and Book Two
        # Books should be (title, author, count) tuples
        book_dict = {(title, author): count for title, author, count in books}
        assert book_dict[("Book One", "Author One")] == 2
        assert book_dict[("Book Two", "Author Two")] == 1

    def test_get_unprocessed_clippings(
        self, temp_db: ClippingsDatabase, sample_clippings: list[Clipping]
    ) -> None:
        """Test getting unprocessed clippings."""
        for clipping in sample_clippings:
            temp_db.insert_clipping(clipping)

        unprocessed = temp_db.get_unprocessed_clippings()
        assert len(unprocessed) == 3

    def test_get_unprocessed_clippings_filtered(
        self, temp_db: ClippingsDatabase, sample_clippings: list[Clipping]
    ) -> None:
        """Test getting unprocessed clippings filtered by book."""
        for clipping in sample_clippings:
            temp_db.insert_clipping(clipping)

        unprocessed = temp_db.get_unprocessed_clippings(
            books=[("Book One", "Author One")]
        )
        assert len(unprocessed) == 2

    def test_get_unsynced_cards(
        self, temp_db: ClippingsDatabase, sample_clipping: Clipping
    ) -> None:
        """Test getting unsynced cards."""
        row_id = temp_db.insert_clipping(sample_clipping)
        assert row_id is not None

        # No unsynced cards initially (no pattern set)
        unsynced = temp_db.get_unsynced_cards()
        assert len(unsynced) == 0

        # Set pattern
        temp_db.update_card_data(row_id, "MENTAL_MODEL", "Front", "Back")

        # Now should have one unsynced card
        unsynced = temp_db.get_unsynced_cards()
        assert len(unsynced) == 1

        # Mark as synced
        temp_db.mark_synced(row_id)

        # Now should have no unsynced cards
        unsynced = temp_db.get_unsynced_cards()
        assert len(unsynced) == 0

    def test_reset_all_generations(
        self, temp_db: ClippingsDatabase, sample_clipping: Clipping
    ) -> None:
        """Test resetting all generations."""
        row_id = temp_db.insert_clipping(sample_clipping)
        assert row_id is not None

        temp_db.update_card_data(row_id, "MENTAL_MODEL", "Front", "Back")
        temp_db.mark_synced(row_id)

        affected = temp_db.reset_all_generations()
        assert affected == 1

        record = temp_db.get_record_by_id(row_id)
        assert record is not None
        assert record.pattern is None
        assert record.front is None
        assert record.back is None
        assert record.synced_to_anki is False

    def test_reset_all_synced(
        self, temp_db: ClippingsDatabase, sample_clipping: Clipping
    ) -> None:
        """Test resetting synced status for all records."""
        row_id = temp_db.insert_clipping(sample_clipping)
        assert row_id is not None

        temp_db.update_card_data(row_id, "MENTAL_MODEL", "Front", "Back")
        temp_db.mark_synced(row_id)

        affected = temp_db.reset_all_synced()
        assert affected == 1

        record = temp_db.get_record_by_id(row_id)
        assert record is not None
        assert record.synced_to_anki is False
        # But pattern should still be set
        assert record.pattern == "MENTAL_MODEL"

    def test_get_unique_books(
        self, temp_db: ClippingsDatabase, sample_clippings: list[Clipping]
    ) -> None:
        """Test getting unique books."""
        for clipping in sample_clippings:
            temp_db.insert_clipping(clipping)

        books = temp_db.get_unique_books()
        assert len(books) == 2
        assert ("Book One", "Author One") in books
        assert ("Book Two", "Author Two") in books

    def test_get_clippings_for_book(
        self, temp_db: ClippingsDatabase, sample_clippings: list[Clipping]
    ) -> None:
        """Test getting clippings for a specific book."""
        for clipping in sample_clippings:
            temp_db.insert_clipping(clipping)

        clippings = temp_db.get_clippings_for_book("Book One", "Author One")
        assert len(clippings) == 2

    def test_get_synced_records(
        self, temp_db: ClippingsDatabase, sample_clippings: list[Clipping]
    ) -> None:
        """Test getting synced records."""
        ids = []
        for clipping in sample_clippings:
            row_id = temp_db.insert_clipping(clipping)
            if row_id:
                ids.append(row_id)

        # Mark first two as synced
        temp_db.update_card_data(ids[0], "PATTERN", "F", "B")
        temp_db.update_card_data(ids[1], "PATTERN", "F", "B")
        temp_db.mark_synced(ids[0])
        temp_db.mark_synced(ids[1])

        synced = temp_db.get_synced_records()
        assert len(synced) == 2

    def test_reset_generations_for_ids(
        self, temp_db: ClippingsDatabase, sample_clippings: list[Clipping]
    ) -> None:
        """Test resetting generations for specific IDs."""
        ids = []
        for clipping in sample_clippings:
            row_id = temp_db.insert_clipping(clipping)
            if row_id:
                ids.append(row_id)
                temp_db.update_card_data(row_id, "PATTERN", "F", "B")
                temp_db.mark_synced(row_id)

        # Reset only first two
        affected = temp_db.reset_generations_for_ids([ids[0], ids[1]])
        assert affected == 2

        # First two should be reset
        record1 = temp_db.get_record_by_id(ids[0])
        assert record1 is not None
        assert record1.pattern is None

        # Third should still have pattern
        record3 = temp_db.get_record_by_id(ids[2])
        assert record3 is not None
        assert record3.pattern == "PATTERN"
