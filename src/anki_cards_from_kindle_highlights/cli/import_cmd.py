"""Import command - import clippings from Kindle."""

from pathlib import Path
from typing import Annotated

import typer

from anki_cards_from_kindle_highlights.clippings import (
    ClippingType,
    parse_clippings_file,
)
from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path


def import_clippings(
    clippings_file: Annotated[
        Path,
        typer.Option(
            "--clippings-file",
            "-c",
            help="Path to Kindle My Clippings.txt file",
            exists=True,
            readable=True,
        ),
    ],
) -> None:
    """Import clippings from a Kindle My Clippings.txt file into the database."""
    db_path = get_db_path()
    print(f"Database location: {db_path}")
    print(f"Reading clippings from: {clippings_file}")

    clippings = parse_clippings_file(clippings_file)
    print(f"Found {len(clippings)} total clippings")

    # Filter to only highlights (skip bookmarks and notes for now)
    highlights = [c for c in clippings if c.clipping_type == ClippingType.HIGHLIGHT]
    print(f"Found {len(highlights)} highlights (filtered out bookmarks/notes)")

    # Get unique books
    books = sorted({c.book_title for c in highlights})
    print(f"Books found: {len(books)}")
    for book in books:
        count = sum(1 for c in highlights if c.book_title == book)
        print(f"  - {book}: {count} highlights")

    db = ClippingsDatabase(db_path)
    inserted = 0
    duplicates = 0

    for clipping in highlights:
        result = db.insert_clipping(clipping)
        if result is not None:
            inserted += 1
        else:
            duplicates += 1

    db.close()

    print()
    print(f"Inserted {inserted} new clippings into database")
    if duplicates > 0:
        print(f"Skipped {duplicates} duplicates (already in database)")
