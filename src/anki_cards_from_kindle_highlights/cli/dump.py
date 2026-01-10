"""Dump command - export database to CSV."""

import csv
from pathlib import Path
from typing import Annotated

import typer

from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path


def dump(
    output_file: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Path to output CSV file",
        ),
    ],
    only_generated: Annotated[
        bool,
        typer.Option(
            "--only-generated",
            help="Only export rows with LLM results (including SKIP)",
        ),
    ] = False,
) -> None:
    """Export the database to a CSV file."""
    db_path = get_db_path()
    print(f"Database location: {db_path}")

    db = ClippingsDatabase(db_path)

    if only_generated:
        records = db.get_generated_records()
        print(f"Exporting {len(records)} generated records")
    else:
        records = db.get_all_records()
        print(f"Exporting {len(records)} total records")

    db.close()

    if not records:
        print("No records to export.")
        return

    # Write to CSV
    fieldnames = [
        "id",
        "book_title",
        "author",
        "clipping_type",
        "page",
        "location_start",
        "location_end",
        "date_added",
        "content",
        "pattern",
        "front",
        "back",
        "imported_at",
        "generated_at",
        "synced_to_anki",
    ]

    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            writer.writerow(
                {
                    "id": record.id,
                    "book_title": record.book_title,
                    "author": record.author,
                    "clipping_type": record.clipping_type.value,
                    "page": record.page,
                    "location_start": record.location_start,
                    "location_end": record.location_end,
                    "date_added": record.date_added.isoformat(),
                    "content": record.content,
                    "pattern": record.pattern,
                    "front": record.front,
                    "back": record.back,
                    "imported_at": record.imported_at.isoformat(),
                    "generated_at": record.generated_at.isoformat()
                    if record.generated_at
                    else None,
                    "synced_to_anki": record.synced_to_anki,
                }
            )

    print(f"Exported to: {output_file}")
