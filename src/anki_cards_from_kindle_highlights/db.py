"""SQLite database for storing clippings and generated Anki cards."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from platformdirs import user_data_dir

from anki_cards_from_kindle_highlights.clippings import Clipping, ClippingType

APP_NAME = "anki-cards-from-kindle-highlights"
DB_FILENAME = "clippings.db"


def get_db_path() -> Path:
    """Get the path to the SQLite database file."""
    data_dir = Path(user_data_dir(APP_NAME))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / DB_FILENAME


@dataclass
class ClippingRecord:
    """A clipping record with LLM-generated card data and sync status."""

    # Database ID
    id: int

    # Clipping fields
    book_title: str
    author: str
    clipping_type: ClippingType
    page: int | None
    location_start: int
    location_end: int | None
    date_added: datetime
    content: str

    # AnkiCardLLMResponse fields
    pattern: str | None
    front: str | None
    back: str | None

    # Timestamps
    imported_at: datetime
    generated_at: datetime | None

    # Sync status
    synced_to_anki: bool


class ClippingsDatabase:
    """SQLite database for storing clippings and generated Anki cards."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the database connection."""
        self.db_path = db_path or get_db_path()
        self._connection: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _ensure_schema(self) -> None:
        """Create the database schema if it doesn't exist."""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clippings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                -- Clipping fields
                book_title TEXT NOT NULL,
                author TEXT,
                clipping_type TEXT NOT NULL,
                page INTEGER,
                location_start INTEGER NOT NULL,
                location_end INTEGER,
                date_added TEXT NOT NULL,
                content TEXT,

                -- AnkiCardLLMResponse fields
                pattern TEXT,
                front TEXT,
                back TEXT,

                -- Timestamps
                imported_at TEXT NOT NULL,
                generated_at TEXT,

                -- Sync status
                synced_to_anki INTEGER NOT NULL DEFAULT 0,

                -- Unique constraint to avoid duplicates
                UNIQUE(book_title, author, content)
            )
        """)
        conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def insert_clipping(self, clipping: Clipping) -> int | None:
        """Insert a clipping into the database. Returns the row ID or None if duplicate."""
        conn = self._get_connection()
        now = datetime.now().isoformat()
        try:
            cursor = conn.execute(
                """
                INSERT INTO clippings (
                    book_title, author, clipping_type, page,
                    location_start, location_end, date_added, content,
                    pattern, front, back, imported_at, generated_at, synced_to_anki
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, 0)
                """,
                (
                    clipping.book_title,
                    clipping.author,
                    clipping.clipping_type.value,
                    clipping.page,
                    clipping.location_start,
                    clipping.location_end,
                    clipping.date_added.isoformat(),
                    clipping.content,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate entry
            return None

    def update_card_data(
        self, record_id: int, pattern: str, front: str | None, back: str | None
    ) -> None:
        """Update the LLM-generated card data for a clipping."""
        conn = self._get_connection()
        now = datetime.now().isoformat()
        conn.execute(
            """
            UPDATE clippings
            SET pattern = ?, front = ?, back = ?, generated_at = ?
            WHERE id = ?
            """,
            (pattern, front, back, now, record_id),
        )
        conn.commit()

    def mark_synced(self, record_id: int) -> None:
        """Mark a clipping as synced to Anki."""
        conn = self._get_connection()
        conn.execute(
            "UPDATE clippings SET synced_to_anki = 1 WHERE id = ?",
            (record_id,),
        )
        conn.commit()

    def get_books_with_unprocessed(self) -> list[tuple[str, str, int]]:
        """Get all books that have unprocessed clippings.

        Returns a list of (book_title, author, count) tuples.
        """
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT book_title, author, COUNT(*) as count
            FROM clippings
            WHERE pattern IS NULL AND content IS NOT NULL
            GROUP BY book_title, author
            ORDER BY book_title
        """)
        return [
            (row["book_title"], row["author"], row["count"])
            for row in cursor.fetchall()
        ]

    def get_unprocessed_clippings(
        self, books: list[tuple[str, str]] | None = None
    ) -> list[ClippingRecord]:
        """Get clippings that haven't been processed by the LLM yet.

        Args:
            books: Optional list of (book_title, author) tuples to filter by.
                   If None, returns all unprocessed clippings.
        """
        if books is None:
            return self._query_records("pattern IS NULL AND content IS NOT NULL")

        # Build WHERE clause for specific books
        conditions = []
        for book_title, author in books:
            # Escape single quotes in strings
            escaped_title = book_title.replace("'", "''")
            escaped_author = author.replace("'", "''")
            conditions.append(
                f"(book_title = '{escaped_title}' AND author = '{escaped_author}')"
            )

        where = (
            f"pattern IS NULL AND content IS NOT NULL AND ({' OR '.join(conditions)})"
        )
        return self._query_records(where)

    def get_unsynced_cards(self) -> list[ClippingRecord]:
        """Get all cards that have been processed but not synced to Anki."""
        return self._query_records(
            "pattern IS NOT NULL AND pattern != 'SKIP' AND synced_to_anki = 0"
        )

    def get_all_records(self) -> list[ClippingRecord]:
        """Get all records from the database."""
        return self._query_records()

    def get_record_by_id(self, record_id: int) -> ClippingRecord | None:
        """Get a single record by its ID."""
        records = self._query_records(f"id = {record_id}")
        return records[0] if records else None

    def get_generated_records(self) -> list[ClippingRecord]:
        """Get all records that have been processed by the LLM (including SKIP)."""
        return self._query_records("pattern IS NOT NULL")

    def reset_all_generations(self) -> int:
        """Reset all LLM-generated fields to NULL and synced_to_anki to False.

        Returns the number of affected rows.
        """
        conn = self._get_connection()
        cursor = conn.execute("""
            UPDATE clippings
            SET pattern = NULL,
                front = NULL,
                back = NULL,
                generated_at = NULL,
                synced_to_anki = 0
            WHERE pattern IS NOT NULL OR synced_to_anki = 1
        """)
        conn.commit()
        return cursor.rowcount

    def reset_all_synced(self) -> int:
        """Reset synced_to_anki to False for all records.

        Returns the number of affected rows.
        """
        conn = self._get_connection()
        cursor = conn.execute("""
            UPDATE clippings
            SET synced_to_anki = 0
            WHERE synced_to_anki = 1
        """)
        conn.commit()
        return cursor.rowcount

    def get_synced_records(self) -> list[ClippingRecord]:
        """Get all records that are marked as synced to Anki."""
        return self._query_records("synced_to_anki = 1")

    def reset_generations_for_ids(self, record_ids: list[int]) -> int:
        """Reset LLM-generated fields for specific record IDs.

        Resets pattern, front, back, generated_at, and synced_to_anki.

        Args:
            record_ids: List of record IDs to reset.

        Returns:
            The number of affected rows.
        """
        if not record_ids:
            return 0

        conn = self._get_connection()
        placeholders = ",".join("?" * len(record_ids))
        cursor = conn.execute(
            f"""
            UPDATE clippings
            SET pattern = NULL,
                front = NULL,
                back = NULL,
                generated_at = NULL,
                synced_to_anki = 0
            WHERE id IN ({placeholders})
            """,
            record_ids,
        )
        conn.commit()
        return cursor.rowcount

    def _query_records(self, where_clause: str | None = None) -> list[ClippingRecord]:
        """Query records with an optional WHERE clause."""
        conn = self._get_connection()
        query = "SELECT * FROM clippings"
        if where_clause:
            query += f" WHERE {where_clause}"

        cursor = conn.execute(query)
        rows = cursor.fetchall()

        return [self._row_to_record(row) for row in rows]

    def get_unique_books(self) -> list[tuple[str, str]]:
        """Get all unique (book_title, author) tuples from the database."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT DISTINCT book_title, author
            FROM clippings
            ORDER BY book_title, author
        """)
        return [(row["book_title"], row["author"]) for row in cursor.fetchall()]

    def get_clippings_for_book(
        self, book_title: str, author: str
    ) -> list[ClippingRecord]:
        """Get all clippings for a specific book.

        Args:
            book_title: The book title to match.
            author: The author name to match.
        """
        escaped_title = book_title.replace("'", "''")
        escaped_author = author.replace("'", "''")
        return self._query_records(
            f"book_title = '{escaped_title}' AND author = '{escaped_author}'"
        )

    def _row_to_record(self, row: sqlite3.Row) -> ClippingRecord:
        """Convert a database row to a ClippingRecord."""
        generated_at_str = row["generated_at"]
        return ClippingRecord(
            id=row["id"],
            book_title=row["book_title"],
            author=row["author"] or "",
            clipping_type=ClippingType(row["clipping_type"]),
            page=row["page"],
            location_start=row["location_start"],
            location_end=row["location_end"],
            date_added=datetime.fromisoformat(row["date_added"]),
            content=row["content"] or "",
            pattern=row["pattern"],
            front=row["front"],
            back=row["back"],
            imported_at=datetime.fromisoformat(row["imported_at"]),
            generated_at=datetime.fromisoformat(generated_at_str)
            if generated_at_str
            else None,
            synced_to_anki=bool(row["synced_to_anki"]),
        )
