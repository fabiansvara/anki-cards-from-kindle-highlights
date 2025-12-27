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
    id: int | None

    # Clipping fields
    book_title: str
    author: str | None
    clipping_type: ClippingType
    page: int | None
    location_start: int
    location_end: int | None
    date_added: datetime
    content: str | None

    # AnkiCardLLMResponse fields
    pattern: str | None
    front: str | None
    back: str | None

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
        try:
            cursor = conn.execute(
                """
                INSERT INTO clippings (
                    book_title, author, clipping_type, page,
                    location_start, location_end, date_added, content,
                    pattern, front, back, synced_to_anki
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0)
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
        conn.execute(
            """
            UPDATE clippings
            SET pattern = ?, front = ?, back = ?
            WHERE id = ?
            """,
            (pattern, front, back, record_id),
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

    def get_unprocessed_clippings(self) -> list[ClippingRecord]:
        """Get all clippings that haven't been processed by the LLM yet."""
        return self._query_records("pattern IS NULL AND content IS NOT NULL")

    def get_unsynced_cards(self) -> list[ClippingRecord]:
        """Get all cards that have been processed but not synced to Anki."""
        return self._query_records(
            "pattern IS NOT NULL AND pattern != 'SKIP' AND synced_to_anki = 0"
        )

    def get_all_records(self) -> list[ClippingRecord]:
        """Get all records from the database."""
        return self._query_records()

    def _query_records(self, where_clause: str | None = None) -> list[ClippingRecord]:
        """Query records with an optional WHERE clause."""
        conn = self._get_connection()
        query = "SELECT * FROM clippings"
        if where_clause:
            query += f" WHERE {where_clause}"

        cursor = conn.execute(query)
        rows = cursor.fetchall()

        return [self._row_to_record(row) for row in rows]

    def _row_to_record(self, row: sqlite3.Row) -> ClippingRecord:
        """Convert a database row to a ClippingRecord."""
        return ClippingRecord(
            id=row["id"],
            book_title=row["book_title"],
            author=row["author"],
            clipping_type=ClippingType(row["clipping_type"]),
            page=row["page"],
            location_start=row["location_start"],
            location_end=row["location_end"],
            date_added=datetime.fromisoformat(row["date_added"]),
            content=row["content"],
            pattern=row["pattern"],
            front=row["front"],
            back=row["back"],
            synced_to_anki=bool(row["synced_to_anki"]),
        )
