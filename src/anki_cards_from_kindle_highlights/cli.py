"""Command-line interface for anki-cards-from-kindle-highlights."""

import csv
import random
from pathlib import Path
from typing import Annotated

import questionary
import typer
from openai import OpenAI
from tqdm import tqdm

from anki_cards_from_kindle_highlights import __version__
from anki_cards_from_kindle_highlights.clippings import (
    ClippingType,
    parse_clippings_file,
)
from anki_cards_from_kindle_highlights.db import ClippingsDatabase, get_db_path
from anki_cards_from_kindle_highlights.llm import llm_highlight_to_card

app = typer.Typer(
    name="anki-cards-from-kindle-highlights",
    help="Generate Anki cards from Kindle highlights using LLMs.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        print(f"anki-cards-from-kindle-highlights {__version__}")
        raise typer.Exit()


def get_prompt() -> str:
    """Load the system prompt from prompt.txt."""
    prompt_file = Path(__file__).parent / "prompt.txt"
    return prompt_file.read_text(encoding="utf-8")


@app.command("generate-one")
def generate_one(
    book_title: Annotated[
        str,
        typer.Option("--book-title", "-b", help="Title of the book"),
    ],
    highlight: Annotated[
        str,
        typer.Option("--highlight", "-h", help="The highlight text to convert"),
    ],
    openai_api_key: Annotated[
        str | None,
        typer.Option(
            "--openai-api-key",
            envvar="OPENAI_API_KEY",
            help="OpenAI API key (defaults to OPENAI_API_KEY env var)",
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="OpenAI model to use"),
    ] = "gpt-4o-2024-08-06",
) -> None:
    """Generate an Anki card from a single highlight (without using the database)."""
    if openai_api_key is None:
        print(
            "Error: OpenAI API key is required. Set OPENAI_API_KEY or use --openai-api-key"
        )
        raise typer.Exit(1)

    client = OpenAI(api_key=openai_api_key)
    prompt = get_prompt()

    card = llm_highlight_to_card(
        client=client,
        prompt=prompt,
        book_title=book_title,
        highlight=highlight,
        model=model,
    )

    if card is None:
        raise typer.Exit(1)

    print(f"Pattern: {card.pattern}")
    print(f"Front: {card.front}")
    print(f"Back: {card.back}")


@app.command()
def generate(
    openai_api_key: Annotated[
        str | None,
        typer.Option(
            "--openai-api-key",
            envvar="OPENAI_API_KEY",
            help="OpenAI API key (defaults to OPENAI_API_KEY env var)",
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="OpenAI model to use"),
    ] = "gpt-4o-2024-08-06",
    max_generations: Annotated[
        int | None,
        typer.Option(
            "--max-generations",
            help="Limit generation to at most this many clippings (for testing)",
        ),
    ] = None,
) -> None:
    """Generate Anki cards for unprocessed clippings in the database."""
    if openai_api_key is None:
        print(
            "Error: OpenAI API key is required. Set OPENAI_API_KEY or use --openai-api-key"
        )
        raise typer.Exit(1)

    db_path = get_db_path()
    print(f"Database location: {db_path}")

    db = ClippingsDatabase(db_path)

    # Get books with unprocessed clippings
    books = db.get_books_with_unprocessed()

    if not books:
        print("No unprocessed clippings found.")
        db.close()
        return

    print(f"Found {len(books)} books with unprocessed clippings\n")

    # Build choices for questionary
    choices = [
        questionary.Choice(
            title=f"{title} ({author or 'Unknown'}) - {count} clippings",
            value=(title, author),
        )
        for title, author, count in books
    ]

    # Let user select books
    selected = questionary.checkbox(
        "Select books to process:",
        choices=choices,
    ).ask()

    if not selected:
        print("No books selected. Exiting.")
        db.close()
        return

    print(f"\nSelected {len(selected)} books")

    # Get unprocessed clippings for selected books
    unprocessed = db.get_unprocessed_clippings(books=selected)

    if not unprocessed:
        print("No unprocessed clippings found for selected books.")
        db.close()
        return

    # Sample if max_generations is set
    if max_generations is not None and max_generations < len(unprocessed):
        random.seed(42)  # Deterministic sampling
        unprocessed = random.sample(unprocessed, max_generations)
        print(
            f"Sampled {len(unprocessed)} clippings (--max-generations {max_generations})\n"
        )
    else:
        print(f"Processing {len(unprocessed)} clippings\n")

    client = OpenAI(api_key=openai_api_key)
    prompt = get_prompt()

    generated = 0
    skipped = 0
    errors = 0

    for record in tqdm(unprocessed, desc="Processing clippings"):
        if record.content is None:
            skipped += 1
            continue

        card = llm_highlight_to_card(
            client=client,
            prompt=prompt,
            book_title=record.book_title,
            highlight=record.content,
            model=model,
        )

        if card is None:
            errors += 1
            continue

        # Update the database with the LLM response (including SKIP)
        db.update_card_data(
            record_id=record.id,
            pattern=card.pattern,
            front=card.front,
            back=card.back,
        )

        if card.pattern == "SKIP":
            skipped += 1
        else:
            generated += 1

    db.close()

    print()
    print(f"Generated {generated} cards")
    print(f"Skipped {skipped} clippings (SKIP or no content)")
    if errors > 0:
        print(f"Errors: {errors}")


@app.command("import")
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
    books = sorted(c.book_title for c in highlights)
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


@app.command()
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


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Generate Anki cards from Kindle highlights using LLMs."""
    _ = version  # Unused, handled by callback


if __name__ == "__main__":
    app()
